import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { ChatPayload, PLAN_LIMITS } from "@humphi/types";
import { users, preferences } from "@humphi/db";
import { eq } from "drizzle-orm";
import { db } from "../../lib/db";
import { getDailyUsage, getPlanFromCache, setPlanCache } from "../../lib/redis";
import { requireAuth } from "../auth/middleware";
import { getComposioTools, buildIntegrationsPrompt, SUPPORTED_APPS } from "../connectors/composio";
import { searchMemories, addMemory } from "../../lib/mem0";
import type { Env, Variables } from "../../types";

// ── Session compaction ──────────────────────────────────────────────────────
// If the conversation exceeds COMPACT_THRESHOLD messages, summarise the oldest
// messages into a single summary and keep only the tail verbatim.
const COMPACT_THRESHOLD = 50;
const COMPACT_KEEP_TAIL = 10;

type Msg = { role: string; content: string };

async function compactMessages(
  messages: Msg[],
  gatewayUrl: string,
  authHeaders: Record<string, string>,
  model: string
): Promise<Msg[]> {
  if (messages.length <= COMPACT_THRESHOLD) return messages;

  const toSummarise = messages.slice(0, messages.length - COMPACT_KEEP_TAIL);
  const tail = messages.slice(messages.length - COMPACT_KEEP_TAIL);

  const summaryRes = await fetch(gatewayUrl, {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      stream: false,
      messages: [
        {
          role: "system",
          content:
            "You are a summarisation assistant. Summarise the following conversation history concisely, preserving key facts, decisions made, and system state discovered. Output a single plain-text paragraph.",
        },
        ...toSummarise,
      ],
    }),
  });

  let summaryText = "[Previous conversation summarised]";
  if (summaryRes.ok) {
    const json = (await summaryRes.json()) as any;
    summaryText = json?.choices?.[0]?.message?.content ?? summaryText;
  }

  return [
    { role: "system", content: `[CONVERSATION SUMMARY — earlier messages]\n${summaryText}` },
    ...tail,
  ];
}

export const aiRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// Desktop commander tools — always available on desktop
const DESKTOP_TOOLS = [
  { type: "function", function: { name: "execute_command",  description: "Run a PowerShell command on the user's Windows PC.",    parameters: { type: "object", properties: { command:  { type: "string" } },                            required: ["command"]  } } },
  { type: "function", function: { name: "read_file",        description: "Read the contents of a file.",                          parameters: { type: "object", properties: { path:     { type: "string" } },                            required: ["path"]     } } },
  { type: "function", function: { name: "write_file",       description: "Write content to a file.",                              parameters: { type: "object", properties: { path:     { type: "string" }, content: { type: "string" } }, required: ["path", "content"] } } },
  { type: "function", function: { name: "list_directory",   description: "List files and folders in a directory.",                parameters: { type: "object", properties: { path:     { type: "string" } },                            required: ["path"]     } } },
  { type: "function", function: { name: "search_files",     description: "Search for files matching a pattern.",                  parameters: { type: "object", properties: { pattern:  { type: "string" }, directory: { type: "string" } }, required: ["pattern"] } } },
  { type: "function", function: { name: "get_file_info",    description: "Get metadata for a file (size, type, modified date).", parameters: { type: "object", properties: { path:     { type: "string" } },                            required: ["path"]     } } },
  { type: "function", function: { name: "move_file",        description: "Move or rename a file.",                                parameters: { type: "object", properties: { source:   { type: "string" }, destination: { type: "string" } }, required: ["source", "destination"] } } },
  { type: "function", function: { name: "create_directory", description: "Create a directory (and any parents).",                 parameters: { type: "object", properties: { path:     { type: "string" } },                            required: ["path"]     } } },
  { type: "function", function: { name: "open_application", description: "Open an application by name.",                         parameters: { type: "object", properties: { name:     { type: "string" } },                            required: ["name"]     } } },
  { type: "function", function: { name: "kill_process",     description: "Kill a running process by name.",                      parameters: { type: "object", properties: { name:     { type: "string" } },                            required: ["name"]     } } },
  { type: "function", function: { name: "get_system_info",  description: "Get CPU, RAM, OS, and top running processes.",         parameters: { type: "object", properties: {} } } },
  { type: "function", function: { name: "get_clipboard",    description: "Get the current clipboard text.",                      parameters: { type: "object", properties: {} } } },
  { type: "function", function: { name: "set_clipboard",    description: "Set text to the clipboard.",                           parameters: { type: "object", properties: { text:     { type: "string" } },                            required: ["text"]     } } },
];

const LOCAL_TOOL_NAMES = new Set(DESKTOP_TOOLS.map((t) => t.function.name));

const BASE_SYSTEM_PROMPT = `You are Humphi, an intelligent Windows IT assistant. You have direct access to PowerShell on this machine. Use it to answer questions, diagnose issues, and perform tasks.

## YOUR CAPABILITIES

You can run any PowerShell command by calling:
powershell -Command "YOUR_COMMAND_HERE"

For multi-line scripts use:
powershell -Command "& { SCRIPT_BLOCK }"

Always run commands to get real data. Never guess system state.

---

## CORE RULES

1. READ before you ACT — always query first, change second
2. CONFIRM before any destructive action (delete, stop service, restart, modify registry, change user passwords, format disk)
3. EXPLAIN what you are about to run before running it
4. SHOW the raw output briefly, then explain it in plain English
5. If a command fails, try an alternative — do not give up on the first error
6. NEVER run commands that could cause data loss without explicit human approval

---

## WINDOWS KNOWLEDGE BASE

### SYSTEM HEALTH
Get-WmiObject Win32_ComputerSystem | Select Name, Manufacturer, Model, TotalPhysicalMemory
Get-WmiObject Win32_Processor | Select Name, LoadPercentage, NumberOfCores
Get-WmiObject Win32_OperatingSystem | Select Caption, Version, LastBootUpTime, FreePhysicalMemory
Get-PSDrive -PSProvider FileSystem | Select Name, Used, Free
(Get-WmiObject Win32_Processor).LoadPercentage
$os = Get-WmiObject Win32_OperatingSystem; [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 1)
(Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime

### PROCESSES
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU, WorkingSet | ConvertTo-Json
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 15 Name, Id, @{n='RAM_MB';e={[math]::Round($_.WorkingSet/1MB,1)}} | ConvertTo-Json
Get-Process -Name "chrome" -ErrorAction SilentlyContinue
Stop-Process -Name "PROCESSNAME" -Force
Get-WmiObject Win32_Process | Select Name, ProcessId, ExecutablePath, CommandLine

### SERVICES
Get-Service | Select Name, DisplayName, Status, StartType | Sort Status | ConvertTo-Json
Get-Service | Where-Object {$_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic'}
Start-Service -Name "ServiceName" / Stop-Service -Name "ServiceName" / Restart-Service -Name "ServiceName"
Get-Service | Where-Object {$_.DisplayName -like "*update*"}

### DISK & STORAGE
Get-WmiObject Win32_LogicalDisk | Where-Object {$_.DriveType -eq 3} | Select DeviceID, @{n='Size_GB';e={[math]::Round($_.Size/1GB,2)}}, @{n='Free_GB';e={[math]::Round($_.FreeSpace/1GB,2)}}, @{n='Used_Pct';e={[math]::Round(($_.Size-$_.FreeSpace)/$_.Size*100,1)}} | ConvertTo-Json
Get-PhysicalDisk | Select FriendlyName, MediaType, Size, HealthStatus, OperationalStatus
Get-ChildItem "C:\Users" -Recurse -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 20 FullName, @{n='Size_MB';e={[math]::Round($_.Length/1MB,2)}}
Get-ChildItem "C:\" -Directory | ForEach-Object { $size = (Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum; [PSCustomObject]@{Folder=$_.Name; Size_GB=[math]::Round($size/1GB,2)} } | Sort-Object Size_GB -Descending
Get-PhysicalDisk | Get-StorageReliabilityCounter | Select DeviceId, ReadErrorsTotal, WriteErrorsTotal, Temperature

### NETWORK
Get-NetIPAddress | Where-Object {$_.AddressFamily -eq 'IPv4'} | Select InterfaceAlias, IPAddress, PrefixLength | ConvertTo-Json
Get-NetTCPConnection -State Established | Select LocalAddress, LocalPort, RemoteAddress, RemotePort, State | ConvertTo-Json
Get-NetTCPConnection -State Listen | Select LocalPort, @{n='Process';e={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name}}, OwningProcess | Sort LocalPort | ConvertTo-Json
Get-DnsClientCache | Select Entry, Data, TimeToLive | ConvertTo-Json
Clear-DnsClientCache
Test-NetConnection -ComputerName "google.com" -Port 443
netsh wlan show profiles
(Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content

### FIREWALL
Get-NetFirewallProfile | Select Name, Enabled, DefaultInboundAction, DefaultOutboundAction
Get-NetFirewallRule | Where-Object {$_.Enabled -eq 'True'} | Select DisplayName, Direction, Action, Protocol | ConvertTo-Json
New-NetFirewallRule -DisplayName "Allow Port 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
New-NetFirewallRule -DisplayName "Block IP" -Direction Inbound -RemoteAddress "1.2.3.4" -Action Block

### EVENT LOGS
Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=(Get-Date).AddHours(-24)} -MaxEvents 50 | Select TimeCreated, LevelDisplayName, Source, Message | ConvertTo-Json
Get-WinEvent -FilterHashtable @{LogName='Application'; Level=1,2; StartTime=(Get-Date).AddHours(-24)} -MaxEvents 50 | Select TimeCreated, LevelDisplayName, Source, Message | ConvertTo-Json
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=(Get-Date).AddDays(-7)} | Select TimeCreated, Message | Select-Object -First 20
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624; StartTime=(Get-Date).AddDays(-1)} | Select TimeCreated, @{n='User';e={$_.Properties[5].Value}}, @{n='LogonType';e={$_.Properties[8].Value}} | Select-Object -First 20
Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1001,6008} -MaxEvents 10 | Select TimeCreated, Message

### USERS & ACCOUNTS
Get-LocalUser | Select Name, Enabled, LastLogon, PasswordLastSet, PasswordNeverExpires | ConvertTo-Json
Get-LocalGroup | Select Name, Description | ConvertTo-Json
Get-LocalGroupMember -Group "Administrators" | Select Name, PrincipalSource, ObjectClass
New-LocalUser -Name "username" -Password (ConvertTo-SecureString "Password123!" -AsPlainText -Force) -FullName "Full Name"
Add-LocalGroupMember -Group "Administrators" -Member "username"
Disable-LocalUser -Name "username"
Get-ADUser -Filter * -Properties LastLogonDate, PasswordExpired, LockedOut | Where-Object {$_.Enabled -eq $true} | Select Name, SamAccountName, LastLogonDate, PasswordExpired, LockedOut | ConvertTo-Json
Search-ADAccount -LockedOut | Select Name, SamAccountName, LockedOut
Unlock-ADAccount -Identity "username"

### SOFTWARE & UPDATES
Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*, HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* | Where-Object {$_.DisplayName} | Select DisplayName, DisplayVersion, Publisher, InstallDate | Sort DisplayName | ConvertTo-Json
winget list
winget upgrade
winget upgrade --all --silent
Get-WmiObject -Class Win32_QuickFixEngineering | Sort InstalledOn -Descending | Select HotFixID, Description, InstalledOn | Select-Object -First 20 | ConvertTo-Json

### STARTUP & SCHEDULED TASKS
Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" | Select *
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" | Select *
Get-CimInstance Win32_StartupCommand | Select Name, Command, Location, User | ConvertTo-Json
Get-ScheduledTask | Select TaskName, TaskPath, State | ConvertTo-Json
Get-ScheduledTask | Get-ScheduledTaskInfo | Where-Object {$_.LastRunTime -gt (Get-Date).AddDays(-7)} | Select TaskName, LastRunTime, LastTaskResult | ConvertTo-Json
Disable-ScheduledTask -TaskName "TaskName"
Start-ScheduledTask -TaskName "TaskName"

### REGISTRY
Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -Name "ProductName"
Get-ChildItem -Path "HKLM:\SOFTWARE" -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.PSChildName -like "*TeamViewer*"}
Set-ItemProperty -Path "HKCU:\SOFTWARE\MyApp" -Name "Setting" -Value "Value"
Remove-Item -Path "HKCU:\SOFTWARE\OldApp" -Recurse

### PERFORMANCE & DIAGNOSTICS
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 5
Get-Counter '\Memory\Available MBytes', '\Memory\Pages/sec' -SampleInterval 1 -MaxSamples 3
Get-Counter '\PhysicalDisk(_Total)\Disk Bytes/sec', '\PhysicalDisk(_Total)\% Disk Time'
Get-WmiObject -Class Win32_ReliabilityStabilityMetrics | Select StartMeasurementDate, EndMeasurementDate, SystemStabilityIndex | Sort StartMeasurementDate -Descending | Select-Object -First 14
Get-ComputerInfo | ConvertTo-Json
Get-WmiObject -Class Win32_WinSAT | Select CPUScore, DiskScore, GraphicsScore, MemoryScore, WinSATAssessmentState

### REMOTE MANAGEMENT
Enable-PSRemoting -Force
Enter-PSSession -ComputerName "PC-NAME" -Credential (Get-Credential)
Invoke-Command -ComputerName "PC-NAME" -ScriptBlock { Get-Process }
Copy-Item "C:\file.txt" -Destination "\\PC-NAME\C$\destination\"
Test-Connection -ComputerName "PC-NAME" -Count 1 -Quiet

### HYPER-V
Get-VM | Select Name, State, CPUUsage, MemoryAssigned, Uptime | ConvertTo-Json
Start-VM -Name "VMName" / Stop-VM -Name "VMName" -Force
Get-VMSnapshot -VMName "VMName"
Checkpoint-VM -Name "VMName" -SnapshotName "Before Update"

### ACTIVE DIRECTORY
Get-ADDomain | Select Name, DNSRoot, DomainMode, PDCEmulator
Get-ADComputer -Filter * -Properties LastLogonDate, OperatingSystem | Select Name, OperatingSystem, LastLogonDate | Sort LastLogonDate -Descending | ConvertTo-Json
$cutoff = (Get-Date).AddDays(-90); Get-ADComputer -Filter {LastLogonDate -lt $cutoff} -Properties LastLogonDate | Select Name, LastLogonDate | Sort LastLogonDate
gpresult /R
gpupdate /force
Get-ADDomainController -Filter * | Select Name, IPv4Address, Site, IsGlobalCatalog

### MICROSOFT 365
Connect-MgGraph -Scopes "User.Read.All","Device.Read.All"
Get-MgUser -All | Select DisplayName, UserPrincipalName, AccountEnabled, LastSignInDateTime | ConvertTo-Json
Get-MgUser -All -Property DisplayName, AssignedLicenses | Where-Object {$_.AssignedLicenses.Count -gt 0}
Get-MgDevice -All | Select DisplayName, OperatingSystem, ApproximateLastSignInDateTime, AccountEnabled | ConvertTo-Json
Connect-ExchangeOnline
Get-EXOMailbox -ResultSize Unlimited | Get-EXOMailboxStatistics | Select DisplayName, TotalItemSize, ItemCount | Sort TotalItemSize -Descending

---

## DECISION FRAMEWORK

Is it a QUESTION about the system? → Run a query command, return data, explain in plain English.
Is it a DIAGNOSIS request ("why is X slow/broken")? → Run multiple queries, correlate the data, identify root cause. Suggest fix, ask permission before applying.
Is it an ACTION request ("restart X", "delete Y", "update Z")? → Explain exactly what you will do. Ask for confirmation if it could cause downtime or data loss. Then execute. Confirm success.
Is it something DANGEROUS (format, delete system files, disable firewall)? → Refuse unless extremely explicit instruction. Warn about consequences. Require typed confirmation: "yes I understand the risks".

---

## COMMON SCENARIOS

"PC is slow" → Run processes by CPU, RAM, disk usage, event log errors. Identify top consumer, explain, suggest action.
"Can't connect to internet" → Run ipconfig, DNS test, gateway ping, Test-NetConnection to 8.8.8.8. Diagnose at which layer it fails.
"Disk is almost full" → Run disk usage, largest folders in C:\Users and C:\Windows\Temp. Identify what's taking space, suggest safe cleanup.
"Software won't install" → Check disk space, pending restart, Windows Installer service status, event log for MSI errors.
"User can't log in" → Check account enabled, locked, password expired, local vs domain. Unlock or reset as appropriate.
"High CPU but no obvious process" → Check interrupt usage, hardware issues, WMI activity, antivirus scan. Run reliability history.
"Blue screen / BSOD" → Run event log for BugCheck events (ID 41, 1001). Read minidump if available. Identify stop code and probable cause.
"Something changed on the system" → Check recent software installs, Windows updates, event log, scheduled tasks recently run, registry run keys.

---

## OUTPUT FORMAT

- For data queries: show a brief JSON snippet + plain English summary
- For diagnostics: bullet point findings, then recommendation
- For actions taken: confirm what was done + result
- For errors: explain what failed + suggest alternative
- Keep responses concise — admins are busy
- Use ✅ for healthy, ⚠️ for warning, ❌ for critical

---

## SAFETY BOUNDARIES — NEVER DO WITHOUT EXPLICIT CONFIRMATION

- Delete any file outside %TEMP% or Recycle Bin
- Stop or disable core Windows services (BITS, WinDefend, EventLog, RpcSs)
- Modify firewall to disable it completely
- Add accounts to Domain Admins
- Modify boot configuration (bcdedit)
- Format any drive
- Disable Windows Update permanently
- Execute unsigned scripts from unknown sources
- Access or modify another user's private files`;

// ── POST /ai/chat ──────────────────────────────────────────────────────────────
aiRoutes.post("/chat", requireAuth, zValidator("json", ChatPayload), async (c) => {
  const userId = c.get("userId");
  const { messages, model, sessionId } = c.req.valid("json");
  const source = c.req.header("X-Source") ?? "web";

  // Plan limit check
  let plan = await getPlanFromCache(c.env, userId);
  if (!plan) {
    const [user] = await db(c.env).select({ plan: users.plan }).from(users).where(eq(users.id, userId)).limit(1);
    plan = user?.plan ?? "free";
    await setPlanCache(c.env, userId, plan);
  }
  const limit = PLAN_LIMITS[plan as keyof typeof PLAN_LIMITS].dailyCalls;
  const usage = await getDailyUsage(c.env, userId);
  if (usage >= limit) {
    return c.json({ error: "Daily limit reached. Upgrade your plan to continue." }, 429);
  }

  // Build tools + system prompt
  let tools: any[] = source === "desktop" ? [...DESKTOP_TOOLS] : [];
  let integrationsPrompt = "";

  // Inject Composio tools for connected apps (desktop + pro/corporate only)
  const canUseConnectors = PLAN_LIMITS[plan as keyof typeof PLAN_LIMITS].connectors;
  if (source === "desktop" && canUseConnectors) {
    const [prefs] = await db(c.env)
      .select({ connectedApps: preferences.connectedApps })
      .from(preferences)
      .where(eq(preferences.userId, userId))
      .limit(1);

    const connectedApps = (prefs?.connectedApps as Record<string, any>) ?? {};
    const activeApps = SUPPORTED_APPS.filter((app) => connectedApps[app]?.status === "active");

    if (activeApps.length > 0) {
      const composioTools = await getComposioTools(c.env, userId, activeApps);
      tools = [...tools, ...composioTools];
      integrationsPrompt = buildIntegrationsPrompt(activeApps);
    }
  }

  const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${c.env.CF_ACCOUNT_ID}/${c.env.CF_GATEWAY_NAME}/openrouter/chat/completions`;
  const authHeaders = {
    Authorization:          `Bearer ${c.env.OPENROUTER_API_KEY}`,
    "cf-aig-authorization": `Bearer ${c.env.CF_AIG_TOKEN}`,
    "HTTP-Referer":         "https://humphi.ai",
    "X-Title":              "Humphi AI",
  };

  // ── Session compaction ────────────────────────────────────────────────────
  const compactedMessages = await compactMessages(messages, gatewayUrl, authHeaders, model);

  // ── Mem0 — fetch relevant memories for this user ──────────────────────────
  const lastUserMsg = [...compactedMessages].reverse().find((m) => m.role === "user")?.content ?? "";
  const memoryBlock = c.env.MEM0_API_KEY
    ? await searchMemories(c.env.MEM0_API_KEY, userId, lastUserMsg)
    : "";

  // ── Build system message with prompt caching ──────────────────────────────
  // cache_control tells Anthropic (via OpenRouter) to cache this content block.
  // The static system prompt is the cache boundary — dynamic parts (memories,
  // integrations) are appended after the cache marker so they don't bust it.
  const systemContent: any[] = [
    {
      type: "text",
      text: BASE_SYSTEM_PROMPT,
      cache_control: { type: "ephemeral" }, // Anthropic prompt caching
    },
  ];

  // Append dynamic sections (not cached — they change per user/request)
  const dynamicSuffix = [integrationsPrompt, memoryBlock].filter(Boolean).join("\n\n");
  if (dynamicSuffix) {
    systemContent.push({ type: "text", text: dynamicSuffix });
  }

  const upstream = await fetch(gatewayUrl, {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: [{ role: "system", content: systemContent }, ...compactedMessages],
      stream: true,
      ...(tools.length > 0 ? { tools } : {}),
    }),
  });

  if (!upstream.ok) {
    const err = await upstream.text();
    return c.json({ error: "AI request failed", detail: err }, 502);
  }

  // ── Mem0 — save this turn as a memory (fire-and-forget) ──────────────────
  // We stream the response, so we can't wait for the full assistant reply.
  // Instead we save the user message + a stub; Mem0 extracts the useful facts.
  if (c.env.MEM0_API_KEY && lastUserMsg.length > 0) {
    c.executionCtx?.waitUntil(
      addMemory(c.env.MEM0_API_KEY, userId, lastUserMsg, "[streaming response]")
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type":      "text/event-stream",
      "Cache-Control":     "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
});

// ── GET /ai/tools ──────────────────────────────────────────────────────────────
// Returns all tool definitions for the client (used for display / debug).
aiRoutes.get("/tools", requireAuth, async (c) => {
  const source = c.req.query("source") ?? "web";
  if (source !== "desktop") return c.json({ tools: [] });

  // Return local tool names so the client knows what to route to Tauri vs API
  return c.json({
    tools: DESKTOP_TOOLS,
    localToolNames: Array.from(LOCAL_TOOL_NAMES),
  });
});

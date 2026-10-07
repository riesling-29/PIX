<#
.SYNOPSIS
Independent streaming source oracle for a local XES or XES.GZ file.
.DESCRIPTION
Uses only .NET, not PIX or another process-mining implementation. Does not
assert PIX compatibility. The XML event digest covers ordered start/end
elements and XML-decoded attribute values, including namespace declarations.
Each token is framed by its unsigned 32-bit big-endian UTF-8 byte length.
The first token is pix.xes.xml-events.v1. A start emits S, qualified element
name, decimal attribute count, then attribute name/value pairs sorted by
ordinal attribute name. An end emits E, qualified element name. An empty
element emits both. Comments, XML declaration, processing instructions and
text are excluded; non-whitespace text is separately reported.

The core sequence digest starts with pix.xes.core-sequence.v1 and uses the
same framing. Each trace emits T; each event emits V followed by presence
(1/0), kind and value of its direct concept:name attribute, then presence,
kind and value of its direct time:timestamp attribute; each trace ends /T.
Absent fields emit 0, empty string, empty string. Globals do not change this
source-level core digest. Duplicate direct keys retain the first occurrence
for core statistics and are explicitly reported; the XML digest retains all.

Patient/case attribute values are not emitted. Activities and lifecycle
values are aggregate histogram labels. Global values are represented by
their SHA256 only. Unexpected metadata XML attributes are SHA256-redacted;
standard metadata (including classifier name and keys) remains visible.
The JSON report is a source inspection, not a PIX test.
Timestamp diagnostics require a calendar date, explicit seconds and zone,
and at most seven fractional second digits. Comparisons are between
successive parseable event timestamps within each trace, skipping unparsed
timestamps. Unparsed counts describe this oracle profile, not XES validity.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$resolvedInput = (Resolve-Path -LiteralPath $InputPath).ProviderPath
if (-not [System.IO.File]::Exists($resolvedInput)) {
    throw 'InputPath must identify an existing file.'
}
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
if ([string]::Equals($resolvedInput, $resolvedOutput, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputPath must differ from the source file.'
}

if (-not ('PixXesSourceOracleV1' -as [type])) {
    Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;

public sealed class PixXesSourceOracleResult {
    public string oracleVersion = "pix.xes.source-oracle.v1";
    public string status = "source-inspected";
    public string sourceFile;
    public long sourceBytes;
    public string sourceSha256;
    public string xmlEventDigest;
    public string coreSequenceDigest;
    public double inspectionSeconds;
    public long traceCount;
    public long eventCount;
    public long emptyTraceCount;
    public long minimumTraceLength = long.MaxValue;
    public long maximumTraceLength;
    public long eventsMissingDirectActivity;
    public long eventsMissingEffectiveActivity;
    public long eventsMissingDirectTimestamp;
    public long eventsMissingEffectiveTimestamp;
    public long eventsInvalidEffectiveTimestamp;
    public long eventsTimestampWithoutTimezone;
    public long eventsTimestampUnsupportedPrecision;
    public string timestampComparisonPolicy = "calendar-date/seconds/explicit-zone; .NET 100ns; successive parseable timestamps per trace; no implicit local timezone";
    public long eventsUsingGlobalActivity;
    public long eventsUsingGlobalTimestamp;
    public long timestampRegressions;
    public long timestampTies;
    public long comparableTimestampPairs;
    public long tracesWithTimestampRegressions;
    public long tracesWithTimestampTies;
    public string earliestTimestampUtc;
    public string latestTimestampUtc;
    public long duplicateAttributeKeys;
    public long nonWhitespaceTextNodes;
    public long processingInstructions;
    public long globalsAfterFirstTrace;
    public long attributesWithoutKey;
    public long primitiveAttributesWithoutValue;
    public Dictionary<string, long> elementCounts = new Dictionary<string, long>();
    public Dictionary<string, long> namespaceCounts = new Dictionary<string, long>();
    public Dictionary<string, long> unknownElementCounts = new Dictionary<string, long>();
    public Dictionary<string, long> invalidStructuralPlacements = new Dictionary<string, long>();
    public Dictionary<string, long> attributeKindCounts = new Dictionary<string, long>();
    public Dictionary<string, long> attributeKeyCounts = new Dictionary<string, long>();
    public Dictionary<string, long> directEventAttributeKeys = new Dictionary<string, long>();
    public Dictionary<string, long> directTraceAttributeKeys = new Dictionary<string, long>();
    public Dictionary<string, long> duplicateKeysByContainer = new Dictionary<string, long>();
    public Dictionary<string, long> activities = new Dictionary<string, long>();
    public Dictionary<string, long> lifecycles = new Dictionary<string, long>();
    public Dictionary<string, long> traceLengthCounts = new Dictionary<string, long>();
    public Dictionary<string, string> rootAttributes = new Dictionary<string, string>();
    public List<Dictionary<string, string>> extensions = new List<Dictionary<string, string>>();
    public List<Dictionary<string, string>> classifiers = new List<Dictionary<string, string>>();
    public List<Dictionary<string, object>> globals = new List<Dictionary<string, object>>();
}

public static class PixXesSourceOracleV1 {
    private static readonly HashSet<string> AttributeKinds = new HashSet<string>(
        new string[] { "string", "date", "int", "float", "boolean", "id", "list", "container" });
    private static readonly HashSet<string> KnownElements = new HashSet<string>(
        new string[] { "log", "trace", "event", "extension", "classifier", "global", "values",
            "string", "date", "int", "float", "boolean", "id", "list", "container" });
    private static readonly Regex TimestampShape = new Regex(
        @"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.([0-9]+))?(?:Z|[+-][0-9]{2}:[0-9]{2})$",
        RegexOptions.CultureInvariant);
    private static readonly Regex TimestampZone = new Regex(@"(?:Z|[+-][0-9]{2}:[0-9]{2})$", RegexOptions.CultureInvariant);

    private sealed class FramedHash : IDisposable {
        private readonly SHA256 algorithm = SHA256.Create();
        private readonly byte[] length = new byte[4];
        public FramedHash(string domain) { Token(domain); }
        public void Token(string value) {
            byte[] bytes = Encoding.UTF8.GetBytes(value);
            uint count = checked((uint)bytes.Length);
            length[0] = (byte)(count >> 24); length[1] = (byte)(count >> 16);
            length[2] = (byte)(count >> 8); length[3] = (byte)count;
            algorithm.TransformBlock(length, 0, 4, length, 0);
            if (bytes.Length != 0) algorithm.TransformBlock(bytes, 0, bytes.Length, bytes, 0);
        }
        public string Finish(string domain) {
            algorithm.TransformFinalBlock(new byte[0], 0, 0);
            return domain + ":sha256:" + Hex(algorithm.Hash);
        }
        public void Dispose() { algorithm.Dispose(); }
    }

    private sealed class Node {
        public string name;
        public string local;
        public Dictionary<string, string> attributes;
        public HashSet<string> childKeys = new HashSet<string>(StringComparer.Ordinal);
    }
    private sealed class Attribute {
        public string kind;
        public string value;
    }
    private sealed class State {
        public PixXesSourceOracleResult result;
        public Stack<Node> stack = new Stack<Node>();
        public Dictionary<string, Attribute> eventAttributes;
        public Dictionary<string, Attribute> eventDefaults = new Dictionary<string, Attribute>();
        public Dictionary<string, object> currentGlobal;
        public List<Dictionary<string, string>> currentGlobalAttributes;
        public long traceLength;
        public bool inTrace;
        public DateTimeOffset? previousTime;
        public DateTimeOffset? earliest;
        public DateTimeOffset? latest;
        public bool traceRegression;
        public bool traceTie;
        public FramedHash xmlHash;
        public FramedHash coreHash;
    }

    private static void Increment(Dictionary<string, long> counts, string key) {
        long previous; counts.TryGetValue(key, out previous); counts[key] = previous + 1;
    }
    private static string Hex(byte[] bytes) {
        return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();
    }
    private static string ValueHash(string value) {
        using (SHA256 hash = SHA256.Create()) return Hex(hash.ComputeHash(Encoding.UTF8.GetBytes(value)));
    }
    private static string Get(Dictionary<string, string> attributes, string key) {
        string value; return attributes.TryGetValue(key, out value) ? value : null;
    }
    private static Dictionary<string, string> Metadata(Node node) {
        Dictionary<string, string> result = new Dictionary<string, string>();
        foreach (KeyValuePair<string, string> item in node.attributes) {
            bool standard = item.Key == "xmlns" || item.Key.StartsWith("xmlns:", StringComparison.Ordinal) ||
                (node.local == "log" && (item.Key == "xes.version" || item.Key == "xes.features" || item.Key == "openxes.version")) ||
                (node.local == "extension" && (item.Key == "name" || item.Key == "prefix" || item.Key == "uri")) ||
                (node.local == "classifier" && (item.Key == "name" || item.Key == "keys")) ||
                (node.local == "global" && item.Key == "scope");
            result[item.Key] = standard ? item.Value : "sha256:" + ValueHash(item.Value);
        }
        return result;
    }
    private static Dictionary<string, string> ReadAttributes(XmlReader reader) {
        Dictionary<string, string> result = new Dictionary<string, string>(StringComparer.Ordinal);
        if (reader.MoveToFirstAttribute()) {
            do { result.Add(reader.Name, reader.Value); } while (reader.MoveToNextAttribute());
            reader.MoveToElement();
        }
        return result;
    }
    private static void Begin(XmlReader reader, State state) {
        Node parent = state.stack.Count == 0 ? null : state.stack.Peek();
        Node node = new Node { name = reader.Name, local = reader.LocalName, attributes = ReadAttributes(reader) };
        PixXesSourceOracleResult report = state.result;
        state.xmlHash.Token("S"); state.xmlHash.Token(node.name);
        state.xmlHash.Token(node.attributes.Count.ToString(CultureInfo.InvariantCulture));
        List<string> names = new List<string>(node.attributes.Keys); names.Sort(StringComparer.Ordinal);
        foreach (string name in names) { state.xmlHash.Token(name); state.xmlHash.Token(node.attributes[name]); }
        Increment(report.elementCounts, node.local);
        Increment(report.namespaceCounts, reader.NamespaceURI);
        if (!KnownElements.Contains(node.local)) Increment(report.unknownElementCounts, node.name);
        if (parent == null) {
            if (node.local != "log") throw new XmlException("Root element is not an XES log.");
            report.rootAttributes = Metadata(node);
        }
        bool directLog = parent != null && parent.local == "log" && state.stack.Count == 1;
        bool directTrace = parent != null && parent.local == "trace" && state.stack.Count == 2 && state.inTrace;
        bool invalidPlacement = (node.local == "log" && parent != null) ||
            (node.local == "trace" && !directLog) || (node.local == "event" && !directTrace) ||
            ((node.local == "global" || node.local == "extension" || node.local == "classifier") && !directLog);
        if (invalidPlacement) Increment(report.invalidStructuralPlacements,
            (parent == null ? "(root)" : parent.local) + " / " + node.local);
        if (directLog && node.local == "extension") report.extensions.Add(Metadata(node));
        if (directLog && node.local == "classifier") report.classifiers.Add(Metadata(node));
        if (directLog && node.local == "global") {
            state.currentGlobal = new Dictionary<string, object>();
            state.currentGlobal["declaration"] = Metadata(node);
            state.currentGlobalAttributes = new List<Dictionary<string, string>>();
            state.currentGlobal["attributes"] = state.currentGlobalAttributes;
            report.globals.Add(state.currentGlobal);
            if (report.traceCount > 0) report.globalsAfterFirstTrace++;
        }
        if (directLog && node.local == "trace") {
            report.traceCount++; state.traceLength = 0; state.inTrace = true;
            state.previousTime = null; state.traceRegression = false; state.traceTie = false;
            state.coreHash.Token("T");
        }
        if (node.local == "event" && directTrace) {
            state.eventAttributes = new Dictionary<string, Attribute>(StringComparer.Ordinal);
        }
        if (AttributeKinds.Contains(node.local)) {
            Increment(report.attributeKindCounts, node.local);
            string key = Get(node.attributes, "key");
            string value = Get(node.attributes, "value");
            if (key == null) report.attributesWithoutKey++;
            else {
                Increment(report.attributeKeyCounts, key);
                if (parent != null && !parent.childKeys.Add(key)) {
                    report.duplicateAttributeKeys++;
                    Increment(report.duplicateKeysByContainer, parent.local + " / " + key);
                }
            }
            if (value == null && node.local != "list" && node.local != "container") report.primitiveAttributesWithoutValue++;
            if (key != null && parent != null && parent.local == "event" && state.stack.Count == 3 && state.eventAttributes != null) {
                Increment(report.directEventAttributeKeys, key);
                if (!state.eventAttributes.ContainsKey(key)) state.eventAttributes.Add(key, new Attribute { kind = node.local, value = value });
            }
            if (key != null && directTrace) Increment(report.directTraceAttributeKeys, key);
            if (parent != null && parent.local == "global" && state.stack.Count == 2 && state.currentGlobal != null) {
                Dictionary<string, string> metadata = new Dictionary<string, string>();
                metadata["key"] = key; metadata["kind"] = node.local;
                metadata["valueSha256"] = value == null ? null : ValueHash(value);
                state.currentGlobalAttributes.Add(metadata);
                if (Get(parent.attributes, "scope") == "event" && key != null && !state.eventDefaults.ContainsKey(key)) {
                    state.eventDefaults.Add(key, new Attribute { kind = node.local, value = value });
                }
            }
        }
        state.stack.Push(node);
        if (reader.IsEmptyElement) End(state);
    }
    private static Attribute Effective(State state, string key, out bool direct) {
        Attribute value; direct = state.eventAttributes.TryGetValue(key, out value);
        if (direct) return value;
        return state.eventDefaults.TryGetValue(key, out value) ? value : null;
    }
    private static void CoreAttribute(State state, string key) {
        Attribute attribute;
        bool present = state.eventAttributes.TryGetValue(key, out attribute);
        state.coreHash.Token(present ? "1" : "0");
        state.coreHash.Token(present ? attribute.kind : "");
        state.coreHash.Token(present ? (attribute.value ?? "") : "");
    }
    private static void EndEvent(State state) {
        PixXesSourceOracleResult report = state.result;
        report.eventCount++; state.traceLength++;
        state.coreHash.Token("V"); CoreAttribute(state, "concept:name"); CoreAttribute(state, "time:timestamp");
        bool direct;
        Attribute activity = Effective(state, "concept:name", out direct);
        if (!direct) report.eventsMissingDirectActivity++;
        if (activity == null || activity.value == null || activity.kind != "string") report.eventsMissingEffectiveActivity++;
        else { Increment(report.activities, activity.value); if (!direct) report.eventsUsingGlobalActivity++; }
        Attribute lifecycle = Effective(state, "lifecycle:transition", out direct);
        if (lifecycle != null && lifecycle.value != null) Increment(report.lifecycles, lifecycle.value);
        Attribute timestamp = Effective(state, "time:timestamp", out direct);
        if (!direct) report.eventsMissingDirectTimestamp++;
        if (timestamp == null || timestamp.value == null) report.eventsMissingEffectiveTimestamp++;
        else {
            if (!direct) report.eventsUsingGlobalTimestamp++;
            DateTimeOffset time;
            Match shape = TimestampShape.Match(timestamp.value);
            bool unsupportedPrecision = shape.Success && shape.Groups[1].Length > 7;
            if (!TimestampZone.IsMatch(timestamp.value)) report.eventsTimestampWithoutTimezone++;
            if (unsupportedPrecision) report.eventsTimestampUnsupportedPrecision++;
            if (timestamp.kind != "date" || !shape.Success || unsupportedPrecision || !DateTimeOffset.TryParse(timestamp.value, CultureInfo.InvariantCulture,
                    DateTimeStyles.None, out time)) report.eventsInvalidEffectiveTimestamp++;
            else {
                if (!state.earliest.HasValue || time < state.earliest.Value) state.earliest = time;
                if (!state.latest.HasValue || time > state.latest.Value) state.latest = time;
                if (state.previousTime.HasValue) {
                    report.comparableTimestampPairs++;
                    if (time < state.previousTime.Value) { report.timestampRegressions++; state.traceRegression = true; }
                    if (time == state.previousTime.Value) { report.timestampTies++; state.traceTie = true; }
                }
                state.previousTime = time;
            }
        }
        state.eventAttributes = null;
    }
    private static void End(State state) {
        Node node = state.stack.Pop();
        Node parent = state.stack.Count == 0 ? null : state.stack.Peek();
        state.xmlHash.Token("E"); state.xmlHash.Token(node.name);
        if (node.local == "event" && parent != null && parent.local == "trace" && state.stack.Count == 2 && state.eventAttributes != null) EndEvent(state);
        if (node.local == "trace" && parent != null && parent.local == "log" && state.stack.Count == 1) {
            state.coreHash.Token("/T");
            PixXesSourceOracleResult report = state.result;
            report.minimumTraceLength = Math.Min(report.minimumTraceLength, state.traceLength);
            report.maximumTraceLength = Math.Max(report.maximumTraceLength, state.traceLength);
            if (state.traceLength == 0) report.emptyTraceCount++;
            if (state.traceRegression) report.tracesWithTimestampRegressions++;
            if (state.traceTie) report.tracesWithTimestampTies++;
            Increment(report.traceLengthCounts, state.traceLength.ToString(CultureInfo.InvariantCulture));
            state.inTrace = false;
        }
        if (node.local == "global" && parent != null && parent.local == "log" && state.stack.Count == 1) {
            state.currentGlobal = null; state.currentGlobalAttributes = null;
        }
    }

    public static PixXesSourceOracleResult Inspect(string path) {
        Stopwatch stopwatch = Stopwatch.StartNew();
        PixXesSourceOracleResult report = new PixXesSourceOracleResult();
        report.sourceFile = Path.GetFileName(path);
        using (FramedHash xmlHash = new FramedHash("pix.xes.xml-events.v1"))
        using (FramedHash coreHash = new FramedHash("pix.xes.core-sequence.v1"))
        using (FileStream input = File.OpenRead(path)) {
            report.sourceBytes = input.Length;
            using (SHA256 hash = SHA256.Create()) report.sourceSha256 = Hex(hash.ComputeHash(input));
            input.Position = 0;
            State state = new State { result = report, xmlHash = xmlHash, coreHash = coreHash };
            XmlReaderSettings settings = new XmlReaderSettings();
            settings.DtdProcessing = DtdProcessing.Prohibit; settings.XmlResolver = null;
            settings.CloseInput = true; settings.IgnoreComments = false; settings.IgnoreWhitespace = false;
            settings.MaxCharactersInDocument = 2147483648L; settings.MaxCharactersFromEntities = 0;
            Stream data = path.EndsWith(".gz", StringComparison.OrdinalIgnoreCase)
                ? (Stream)new GZipStream(input, CompressionMode.Decompress) : input;
            using (data) using (XmlReader reader = XmlReader.Create(data, settings)) {
                while (reader.Read()) {
                    if (reader.NodeType == XmlNodeType.Element) Begin(reader, state);
                    else if (reader.NodeType == XmlNodeType.EndElement) End(state);
                    else if ((reader.NodeType == XmlNodeType.Text || reader.NodeType == XmlNodeType.CDATA ||
                              reader.NodeType == XmlNodeType.SignificantWhitespace) && !String.IsNullOrWhiteSpace(reader.Value)) report.nonWhitespaceTextNodes++;
                    else if (reader.NodeType == XmlNodeType.ProcessingInstruction) report.processingInstructions++;
                }
            }
            report.xmlEventDigest = xmlHash.Finish("pix.xes.xml-events.v1");
            report.coreSequenceDigest = coreHash.Finish("pix.xes.core-sequence.v1");
            report.earliestTimestampUtc = state.earliest.HasValue ? state.earliest.Value.UtcDateTime.ToString("o", CultureInfo.InvariantCulture) : null;
            report.latestTimestampUtc = state.latest.HasValue ? state.latest.Value.UtcDateTime.ToString("o", CultureInfo.InvariantCulture) : null;
        }
        if (report.traceCount == 0) report.minimumTraceLength = 0;
        stopwatch.Stop(); report.inspectionSeconds = Math.Round(stopwatch.Elapsed.TotalSeconds, 6);
        return report;
    }
}
'@
}

$report = [PixXesSourceOracleV1]::Inspect($resolvedInput)
$outputDirectory = [System.IO.Path]::GetDirectoryName($resolvedOutput)
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$json = $report | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($resolvedOutput, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
[pscustomobject]@{
    File = $report.sourceFile
    Traces = $report.traceCount
    Events = $report.eventCount
    EmptyTraces = $report.emptyTraceCount
    MissingActivity = $report.eventsMissingEffectiveActivity
    MissingTimestamp = $report.eventsMissingEffectiveTimestamp
    InvalidTimestamp = $report.eventsInvalidEffectiveTimestamp
    DuplicateKeys = $report.duplicateAttributeKeys
    XmlDigest = $report.xmlEventDigest
    Report = $resolvedOutput
}

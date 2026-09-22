using System.Text.Json;
using System.Text.Json.Nodes;
using Synapse.Generator.Configuration;
using Synapse.Generator.Domain.Graph;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Resolution;
using Synapse.Generator.Git;
using Synapse.Generator.Parsing;
using Synapse.Generator.Pipeline;
using Synapse.Generator.Scanning;
using Synapse.Generator.Serialization;

// ── Argument parsing ──────────────────────────────────────────────────────────

string? vaultPath  = null;
string? configPath = null;
string? outputPath = null;
var skipGitHistory = args.Contains("--no-git");

for (var i = 0; i < args.Length - 1; i++)
{
    switch (args[i])
    {
        case "--vault":  vaultPath  = args[i + 1]; break;
        case "--config": configPath = args[i + 1]; break;
        case "--out":    outputPath = args[i + 1]; break;
    }
}

if (vaultPath is null)
{
    Console.Error.WriteLine(
        "Usage: Synapse.Generator --vault <path> [--config <path>] [--out <path>] [--no-git]");
    return 1;
}

vaultPath = Path.GetFullPath(vaultPath);
outputPath ??= Path.Combine(Path.GetDirectoryName(vaultPath)!, "graph.json");

// ── Load configuration ────────────────────────────────────────────────────────

FrontmatterMapConfig frontmatterMap;

if (configPath is not null)
{
    frontmatterMap = LoadFromFile(configPath);
}
else
{
    // Fall back to the embedded generator.config.json
    using var stream = typeof(Program).Assembly
        .GetManifestResourceStream(
            "Synapse.Generator.Configuration.generator.config.json")!;
    frontmatterMap = ParseFrontmatterMap(stream);
}

var config = new GeneratorConfig(frontmatterMap, vaultPath, outputPath, skipGitHistory);

// ── Build and run pipeline ────────────────────────────────────────────────────

var pipeline = new GeneratorPipeline(
    new FileSystemVaultScanner(),
    new YamlFrontmatterReader(),
    new WikiLinkExtractor(new MarkdigNoteParser()),
    new GitHistoryReader(),
    new ConfigurableFrontmatterMapper(frontmatterMap),
    new LinkResolver(),
    new GraphBuilder());

var (graph, rawNotes) = pipeline.Run(config);

// ── Serialize graph.json ──────────────────────────────────────────────────────

var serializer   = new JsonGraphSerializer();
var vaultName    = Path.GetFileName(vaultPath);
var generatedAt  = DateTime.UtcNow.ToString("O");
var json         = serializer.Serialize(graph, vaultName, generatedAt);

serializer.WriteAtomic(outputPath, json);

// ── Serialize search-index.json ───────────────────────────────────────────────

var searchOutputPath = Path.Combine(
    Path.GetDirectoryName(Path.GetFullPath(outputPath))!,
    "search-index.json");

var titleById = graph.Nodes
    .OfType<RealGraphNode>()
    .ToDictionary(n => n.Id, n => n.Title, StringComparer.Ordinal);

var searchSerializer = new SearchIndexSerializer();
var searchJson       = searchSerializer.Serialize(rawNotes, titleById);
searchSerializer.WriteAtomic(searchOutputPath, searchJson);

// ── Summary ───────────────────────────────────────────────────────────────────

var realCount  = graph.Nodes.OfType<RealGraphNode>().Count();
var ghostCount = graph.Nodes.OfType<GhostGraphNode>().Count();
Console.WriteLine(
    $"Generated graph.json: {realCount} nodes ({ghostCount} ghosts), {graph.Edges.Count} edges");
Console.WriteLine(
    $"Generated search-index.json: {titleById.Count} entries");

return 0;

// ── Local helpers ─────────────────────────────────────────────────────────────

static FrontmatterMapConfig LoadFromFile(string path)
{
    using var fs = File.OpenRead(path);
    return ParseFrontmatterMap(fs);
}

static FrontmatterMapConfig ParseFrontmatterMap(Stream stream)
{
    using var doc = JsonDocument.Parse(stream);
    if (!doc.RootElement.TryGetProperty("frontmatterMap", out var fm))
        return new FrontmatterMapConfig();

    return new FrontmatterMapConfig(
        CategoryKey: GetStr(fm, "categoryKey") ?? "category",
        LevelKey:    GetStr(fm, "levelKey")    ?? "level",
        StatusKey:   GetStr(fm, "statusKey")   ?? "status",
        TagsKey:     GetStr(fm, "tagsKey")     ?? "tags",
        AliasesKey:  GetStr(fm, "aliasesKey")  ?? "aliases",
        TitleKey:    GetStr(fm, "titleKey")    ?? "title",
        ModifiedKey: GetStr(fm, "modifiedKey") ?? "modified",
        TypeKey:     GetStr(fm, "typeKey")     ?? "type",
        RelationsKey:GetStr(fm, "relationsKey")?? "relations"
    );
}

static string? GetStr(JsonElement el, string name) =>
    el.TryGetProperty(name, out var prop) &&
    prop.ValueKind == JsonValueKind.String
        ? prop.GetString()
        : null;

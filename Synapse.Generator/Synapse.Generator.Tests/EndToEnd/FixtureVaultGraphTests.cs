using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FluentAssertions;
using NJsonSchema;
using Synapse.Generator.Configuration;
using Synapse.Generator.Domain.Graph;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Resolution;
using Synapse.Generator.Git;
using Synapse.Generator.Parsing;
using Synapse.Generator.Pipeline;
using Synapse.Generator.Scanning;
using Synapse.Generator.Serialization;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.EndToEnd;

/// <summary>
/// Full pipeline integration test against the fixture vault.
/// </summary>
public class FixtureVaultGraphTests
{
    private static string VaultRoot => FixtureVaultPath.GetPath();

    // Path to the schema file (navigate from assembly → project → repo root)
    private static string SchemaPath
    {
        get
        {
            var assemblyDir = Path.GetDirectoryName(
                typeof(FixtureVaultGraphTests).Assembly.Location)!;
            // bin/Debug/net8.0 → ../../../ → Tests project → ../../../../ → repo root
            var projectDir = Path.GetFullPath(Path.Combine(assemblyDir, "..", "..", ".."));
            var repoRoot   = Path.GetFullPath(Path.Combine(projectDir, "..", ".."));
            return Path.Combine(repoRoot, "schema", "graph.schema.v2.json");
        }
    }

    // Golden file path relative to the Tests project
    private static string GoldenPath
    {
        get
        {
            var assemblyDir = Path.GetDirectoryName(
                typeof(FixtureVaultGraphTests).Assembly.Location)!;
            var projectDir = Path.GetFullPath(Path.Combine(assemblyDir, "..", "..", ".."));
            return Path.Combine(projectDir, "Fixtures", "golden-graph.json");
        }
    }

    // Lazy fixture: build once, reuse across tests in the same run.
    private static readonly Lazy<(KnowledgeGraph Graph, string Json)> _fixture =
        new(RunPipeline);

    private static (KnowledgeGraph Graph, string Json) RunPipeline()
    {
        var config = new GeneratorConfig(
            new FrontmatterMapConfig(),
            VaultRoot,
            Path.Combine(Path.GetTempPath(), $"synapse-test-{Guid.NewGuid():N}.json"));

        var pipeline = new GeneratorPipeline(
            new FileSystemVaultScanner(),
            new YamlFrontmatterReader(),
            new WikiLinkExtractor(new MarkdigNoteParser()),
            new GitHistoryReader(),
            new ConfigurableFrontmatterMapper(new FrontmatterMapConfig()),
            new LinkResolver(),
            new GraphBuilder());

        var (graph, _) = pipeline.Run(config);
        var serializer = new JsonGraphSerializer();
        var json       = serializer.Serialize(graph, "Vault", "2026-01-01T00:00:00.0000000Z");

        return (graph, json);
    }

    // ── Schema validation ─────────────────────────────────────────────────────

    [Fact]
    public async Task Output_ValidatesAgainstSchemaV2()
    {
        var json = _fixture.Value.Json;

        var schemaJson = await File.ReadAllTextAsync(SchemaPath);
        var schema     = await JsonSchema.FromJsonAsync(schemaJson);
        var errors     = schema.Validate(json);

        errors.Should().BeEmpty(
            because: $"graph.json must conform to graph.schema.v2.json; errors: " +
                     string.Join("; ", errors.Select(e => e.ToString())));
    }

    // ── Node counts ───────────────────────────────────────────────────────────

    [Fact]
    public void Graph_HasNineRealNodes()
    {
        var realCount = _fixture.Value.Graph.Nodes.OfType<RealGraphNode>().Count();
        realCount.Should().Be(9);
    }

    [Fact]
    public void Graph_HasTwoGhostNodes()
    {
        // One from a dangling [[wikilink]], one from a typed relation pointing outside
        // the vault — an unresolved relation must be visible, not silently dropped.
        var ghostCount = _fixture.Value.Graph.Nodes.OfType<GhostGraphNode>().Count();
        ghostCount.Should().Be(2);
    }

    [Fact]
    public void GhostNodes_CoverBothWikilinkAndRelationTargets()
    {
        var ghosts = _fixture.Value.Graph.Nodes
            .OfType<GhostGraphNode>()
            .Select(g => g.Id)
            .ToList();

        ghosts.Should().BeEquivalentTo(["kubernetes advanced", "kernel-internals"]);
    }

    // ── Orphans ───────────────────────────────────────────────────────────────

    [Fact]
    public void OrphanSet_ContainsVimShortcuts()
    {
        var orphans = _fixture.Value.Graph.OrphanIds();
        orphans.Should().Contain("vim-shortcuts");
    }

    // ── Git history ───────────────────────────────────────────────────────────

    [Fact]
    public void AllRealNodes_HaveNonEmptyHistory()
    {
        var noHistory = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Where(n => n.History.Count == 0)
            .Select(n => n.Id)
            .ToList();

        noHistory.Should().BeEmpty(
            because: "all fixture vault notes are committed to the fixture git repo");
    }

    // ── JSON structure ────────────────────────────────────────────────────────

    [Fact]
    public void SerializedJson_HasSchemaVersion2()
    {
        var doc = JsonDocument.Parse(_fixture.Value.Json);
        doc.RootElement.GetProperty("schemaVersion").GetInt32()
            .Should().Be(JsonGraphSerializer.SchemaVersion).And.Be(2);
    }

    [Fact]
    public void SerializedJson_VaultMetaIsConsistent()
    {
        var doc  = JsonDocument.Parse(_fixture.Value.Json);
        var vault = doc.RootElement.GetProperty("vault");

        vault.GetProperty("notesCount").GetInt32().Should().Be(9);
        vault.GetProperty("ghostCount").GetInt32().Should().Be(2);
        // At least one orphan (vim-shortcuts)
        vault.GetProperty("orphanCount").GetInt32().Should().BeGreaterThanOrEqualTo(1);
    }

    // ── Node type and edge kind (schema v2) ───────────────────────────────────

    [Fact]
    public void NoteType_IsCarriedFromFrontmatter_AndAbsentWhenNotDeclared()
    {
        var byId = _fixture.Value.Graph.Nodes.OfType<RealGraphNode>().ToDictionary(n => n.Id);

        byId["docker-basics"].NoteType.Should().Be("file");
        byId["dockerfile"].NoteType.Should().BeNull(
            because: "a vault may type only some of its notes");
    }

    [Fact]
    public void PlainWikilinks_AreEdgesOfKindLink()
    {
        var edge = _fixture.Value.Graph.Edges
            .Single(e => e.Source == "docker-basics" && e.Target == "linux-fundamentals");

        edge.Kind.Should().Be(EdgeKinds.Link);
        edge.Confidence.Should().BeNull();
    }

    [Fact]
    public void TypedRelation_BecomesAnEdgeCarryingItsKindAndConfidence()
    {
        var edge = _fixture.Value.Graph.Edges
            .Single(e => e.Source == "docker-basics" && e.Target == "dockerfile");

        edge.Kind.Should().Be("near_duplicate");
        edge.Confidence.Should().BeApproximately(0.82, 0.0001);
    }

    [Fact]
    public void UnresolvedRelation_BecomesAGhostEdgeKeepingItsKind()
    {
        var edge = _fixture.Value.Graph.Edges
            .Single(e => e.Source == "linux-fundamentals" && e.Target == "kernel-internals");

        edge.Kind.Should().Be("older_version");
    }

    [Fact]
    public void SerializedEdges_CarryKind_AndConfidenceOnlyWhenDeclared()
    {
        var doc   = JsonDocument.Parse(_fixture.Value.Json);
        var edges = doc.RootElement.GetProperty("edges").EnumerateArray().ToList();

        edges.Should().AllSatisfy(e =>
            e.TryGetProperty("kind", out _).Should().BeTrue(
                because: "the viewer styles every edge by its kind"));

        var typed = edges.Single(e =>
            e.GetProperty("source").GetString() == "docker-basics" &&
            e.GetProperty("target").GetString() == "dockerfile");
        typed.GetProperty("confidence").GetDouble().Should().BeApproximately(0.82, 0.0001);

        var plain = edges.Single(e =>
            e.GetProperty("source").GetString() == "docker-basics" &&
            e.GetProperty("target").GetString() == "linux-fundamentals");
        plain.TryGetProperty("confidence", out _).Should().BeFalse();
    }

    // ── Snapshot / golden file ────────────────────────────────────────────────

    [Fact]
    public void Json_MatchesGoldenFile_OrCreatesItOnFirstRun()
    {
        // Normalise generatedAt so the comparison is deterministic
        var actualJson = NormalizeGeneratedAt(_fixture.Value.Json);

        if (!File.Exists(GoldenPath))
        {
            // First run: save the golden file and pass
            File.WriteAllText(GoldenPath, actualJson, Encoding.UTF8);
            return;
        }

        var goldenJson = NormalizeGeneratedAt(File.ReadAllText(GoldenPath));
        actualJson.Should().Be(goldenJson,
            because: "deterministic pipeline output must match the checked-in golden file");
    }

    // Replace the generatedAt timestamp with a sentinel so snapshot comparisons
    // are not invalidated by wall-clock differences.
    private static string NormalizeGeneratedAt(string json) =>
        Regex.Replace(json,
            @"""generatedAt""\s*:\s*""[^""]+""",
            @"""generatedAt"": ""__NORMALIZED__""");
}

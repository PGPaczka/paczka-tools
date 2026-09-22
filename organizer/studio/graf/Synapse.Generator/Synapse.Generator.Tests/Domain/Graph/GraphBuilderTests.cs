using FluentAssertions;
using Synapse.Generator.Configuration;
using Synapse.Generator.Domain.Graph;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;
using Synapse.Generator.Domain.Resolution;
using Synapse.Generator.Git;
using Synapse.Generator.Parsing;
using Synapse.Generator.Pipeline;
using Synapse.Generator.Scanning;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Domain.Graph;

/// <summary>
/// Tests for <see cref="GraphBuilder"/> using the full fixture vault as input data.
/// All stages up to (but not including) GraphBuilder are run with real implementations.
/// </summary>
public class GraphBuilderTests
{
    private static string VaultRoot => FixtureVaultPath.GetPath();

    // Parsed once per test class via a lazy initialiser.
    private static readonly Lazy<(
        IReadOnlyList<RawNote> Notes,
        IReadOnlyDictionary<string, MappedFrontmatter> Frontmatters,
        IReadOnlyList<ResolvedLink> Links,
        IReadOnlyDictionary<string, IReadOnlyList<string>> History,
        IReadOnlyList<Warning> Warnings,
        KnowledgeGraph Graph
    )> _fixture = new(BuildFixture);

    private static (
        IReadOnlyList<RawNote> Notes,
        IReadOnlyDictionary<string, MappedFrontmatter> Frontmatters,
        IReadOnlyList<ResolvedLink> Links,
        IReadOnlyDictionary<string, IReadOnlyList<string>> History,
        IReadOnlyList<Warning> Warnings,
        KnowledgeGraph Graph
    ) BuildFixture()
    {
        var scanner = new FileSystemVaultScanner();
        var frontmatterReader = new YamlFrontmatterReader();
        var parser = new MarkdigNoteParser();
        var extractor = new WikiLinkExtractor(parser);
        var gitReader = new GitHistoryReader();
        var mapper = new ConfigurableFrontmatterMapper(new FrontmatterMapConfig());
        var resolver = new LinkResolver();
        var builder = new GraphBuilder();

        var files = scanner.GetNoteFiles(VaultRoot);
        var rawNotes = new List<RawNote>();
        var historyById = new Dictionary<string, IReadOnlyList<string>>();

        foreach (var filePath in files)
        {
            var content = File.ReadAllText(filePath);
            var relativePath = Path.GetRelativePath(VaultRoot, filePath);
            var id = Path.GetFileNameWithoutExtension(filePath);
            var frontmatter = frontmatterReader.Read(content);
            var wikiLinks = extractor.Extract(content);
            var history = gitReader.GetHistory(VaultRoot, filePath);
            var body = GeneratorPipeline.ExtractBody(content);

            rawNotes.Add(new RawNote(id, relativePath, frontmatter, wikiLinks, body));
            historyById[id] = history;
        }

        var frontmatters = rawNotes.ToDictionary(
            n => n.Id, n => mapper.Map(n.Frontmatter, n.RelativePath));

        var (links, warnings) = resolver.Resolve(rawNotes, frontmatters);
        var graph = builder.Build(rawNotes, frontmatters, links, historyById, warnings);

        return (rawNotes, frontmatters, links, historyById, warnings, graph);
    }

    // ── Ghost nodes ───────────────────────────────────────────────────────────

    [Fact]
    public void GhostNodes_ComeFromBothWikilinksAndTypedRelations()
    {
        var graph = _fixture.Value.Graph;
        var ghosts = graph.Nodes.OfType<GhostGraphNode>().ToList();

        ghosts.Select(g => g.Id).Should().BeEquivalentTo(
            ["kubernetes advanced", "kernel-internals"],
            because: "a dangling [[wikilink]] and a relation pointing outside the vault "
                     + "must both stay visible instead of being dropped");
    }

    [Fact]
    public void KubernetesAdvancedGhost_ReferencedByBothNotes()
    {
        var ghost = _fixture.Value.Graph.Nodes
            .OfType<GhostGraphNode>()
            .Single(g => g.Id == "kubernetes advanced");

        ghost.ReferencedBy.Should().Contain("kubernetes-intro");
        ghost.ReferencedBy.Should().Contain("docker-volumes");
        ghost.ReferenceCount.Should().Be(2);
    }

    // ── Orphans ───────────────────────────────────────────────────────────────

    [Fact]
    public void VimShortcuts_IsAnOrphan()
    {
        var orphans = _fixture.Value.Graph.OrphanIds();
        orphans.Should().Contain("vim-shortcuts",
            because: "vim-shortcuts has no links in or out");
    }

    [Fact]
    public void LinuxFundamentals_IsNotAnOrphan()
    {
        var orphans = _fixture.Value.Graph.OrphanIds();
        orphans.Should().NotContain("linux-fundamentals",
            because: "docker-basics and process-scheduling both link to it");
    }

    // ── Real nodes ────────────────────────────────────────────────────────────

    [Fact]
    public void NineRealNodes_OnePerFixtureFile()
    {
        var realCount = _fixture.Value.Graph.Nodes.OfType<RealGraphNode>().Count();
        realCount.Should().Be(9);
    }

    [Fact]
    public void DockerBasics_MappedCorrectly()
    {
        var node = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Single(n => n.Id == "docker-basics");

        node.Title.Should().Be("Docker Basics");
        node.Category.Should().Be("DevOps");
        node.Level.Should().Be(1);
        node.Status.Should().Be("completed");
        node.Tags.Should().Contain("containers");
    }

    [Fact]
    public void DockerCompose_MissingCategory_DefaultsToUncategorized()
    {
        var node = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Single(n => n.Id == "docker-compose");

        node.Category.Should().Be("Uncategorized");
    }

    [Fact]
    public void DockerNetworking_MissingLevel_IsNull()
    {
        var node = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Single(n => n.Id == "docker-networking");

        node.Level.Should().BeNull();
    }

    // ── Excerpt / WordCount ───────────────────────────────────────────────────

    [Fact]
    public void AllRealNodes_HaveNonEmptyExcerpt()
    {
        var empties = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Where(n => string.IsNullOrWhiteSpace(n.Excerpt))
            .Select(n => n.Id)
            .ToList();

        empties.Should().BeEmpty();
    }

    [Fact]
    public void AllRealNodes_HavePositiveWordCount()
    {
        var zeros = _fixture.Value.Graph.Nodes
            .OfType<RealGraphNode>()
            .Where(n => n.WordCount <= 0)
            .Select(n => n.Id)
            .ToList();

        zeros.Should().BeEmpty();
    }
}

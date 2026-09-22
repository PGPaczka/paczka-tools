using Synapse.Generator.Configuration;
using Synapse.Generator.Domain.Graph;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;
using Synapse.Generator.Domain.Resolution;
using Synapse.Generator.Git;
using Synapse.Generator.Parsing;
using Synapse.Generator.Scanning;

namespace Synapse.Generator.Pipeline;

/// <summary>
/// Orchestrates all generator stages:
/// VaultScanner → (foreach: FrontmatterReader + WikiLinkExtractor + GitHistoryReader)
///   → FrontmatterMapper → LinkResolver → GraphBuilder
/// </summary>
public class GeneratorPipeline
{
    private readonly IVaultScanner _scanner;
    private readonly IFrontmatterReader _frontmatterReader;
    private readonly WikiLinkExtractor _wikiLinkExtractor;
    private readonly IGitHistoryReader _gitHistoryReader;
    private readonly IFrontmatterMapper _mapper;
    private readonly ILinkResolver _resolver;
    private readonly GraphBuilder _builder;

    public GeneratorPipeline(
        IVaultScanner scanner,
        IFrontmatterReader frontmatterReader,
        WikiLinkExtractor wikiLinkExtractor,
        IGitHistoryReader gitHistoryReader,
        IFrontmatterMapper mapper,
        ILinkResolver resolver,
        GraphBuilder builder)
    {
        _scanner          = scanner;
        _frontmatterReader = frontmatterReader;
        _wikiLinkExtractor = wikiLinkExtractor;
        _gitHistoryReader  = gitHistoryReader;
        _mapper            = mapper;
        _resolver          = resolver;
        _builder           = builder;
    }

    /// <summary>
    /// Runs the full pipeline and returns the assembled graph together with the raw notes
    /// (which carry the full body markdown needed for the search index).
    /// </summary>
    public (KnowledgeGraph Graph, IReadOnlyList<RawNote> RawNotes) Run(GeneratorConfig config)
    {
        var vaultPath = config.VaultPath;

        // ── 1. Scan ──────────────────────────────────────────────────────────
        var files = _scanner.GetNoteFiles(vaultPath);

        // ── 2. Parse each file ───────────────────────────────────────────────
        var rawNotes    = new List<RawNote>(files.Count);
        var historyById = new Dictionary<string, IReadOnlyList<string>>(files.Count);

        foreach (var filePath in files)
        {
            var content      = File.ReadAllText(filePath);
            var relativePath = Path.GetRelativePath(vaultPath, filePath);
            var id           = Path.GetFileNameWithoutExtension(filePath);

            var frontmatter = _frontmatterReader.Read(content);
            var wikiLinks   = _wikiLinkExtractor.Extract(content);
            // Skipping git is not an optimisation detail: a generated vault usually is not a
            // repository, and one failing `git log` per note costs a process each time.
            var history     = config.SkipGitHistory
                ? []
                : _gitHistoryReader.GetHistory(vaultPath, filePath);
            var body        = ExtractBody(content);

            rawNotes.Add(new RawNote(id, relativePath, frontmatter, wikiLinks, body));
            historyById[id] = history;
        }

        // ── 3. Map frontmatter ───────────────────────────────────────────────
        var frontmatters = rawNotes.ToDictionary(
            n => n.Id,
            n => _mapper.Map(n.Frontmatter, n.RelativePath));

        // ── 4. Resolve links ─────────────────────────────────────────────────
        var (links, warnings) = _resolver.Resolve(rawNotes, frontmatters);

        // ── 5. Build graph ───────────────────────────────────────────────────
        var graph = _builder.Build(rawNotes, frontmatters, links, historyById, warnings);
        return (graph, rawNotes);
    }

    /// <summary>
    /// Extracts the markdown body from a note's raw content (everything after the
    /// closing front-matter fence). Public for use in tests.
    /// </summary>
    public static string ExtractBody(string content)
    {
        if (!content.StartsWith("---", StringComparison.Ordinal))
            return content;

        var afterOpen = content.IndexOf('\n');
        if (afterOpen < 0) return string.Empty;
        afterOpen++;

        var closePos = content.IndexOf("\n---", afterOpen, StringComparison.Ordinal);
        if (closePos < 0) return content[afterOpen..];

        // Skip past "\n---"
        var bodyStart = closePos + 4;
        // Also skip the newline that follows the closing fence
        if (bodyStart < content.Length && content[bodyStart] == '\n')
            bodyStart++;

        return bodyStart < content.Length ? content[bodyStart..] : string.Empty;
    }
}

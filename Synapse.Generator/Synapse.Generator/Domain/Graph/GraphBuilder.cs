using System.Text.RegularExpressions;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;
using Synapse.Generator.Domain.Resolution;

namespace Synapse.Generator.Domain.Graph;

/// <summary>
/// Assembles a <see cref="KnowledgeGraph"/> from pre-processed pipeline data.
/// Pure — no IO.
/// </summary>
public class GraphBuilder
{
    private static readonly Regex MarkdownChars =
        new(@"[#>*`\[\]]", RegexOptions.Compiled);

    private static readonly Regex MultiSpace =
        new(@"\s+", RegexOptions.Compiled);

    private static readonly char[] WhitespaceSeparators =
        [' ', '\t', '\n', '\r'];

    public KnowledgeGraph Build(
        IReadOnlyList<RawNote> notes,
        IReadOnlyDictionary<string, MappedFrontmatter> frontmatters,
        IReadOnlyList<ResolvedLink> links,
        IReadOnlyDictionary<string, IReadOnlyList<string>> historyById,
        IReadOnlyList<Warning> warnings)
    {
        // ── 1. Real nodes ─────────────────────────────────────────────────────
        var realNodes = new List<GraphNode>(notes.Count);

        foreach (var note in notes)
        {
            var fm = frontmatters.TryGetValue(note.Id, out var mapped)
                ? mapped
                : new MappedFrontmatter(note.Id, "Uncategorized", null, null, [], [], null, null, []);

            var history = historyById.TryGetValue(note.Id, out var h) ? h : [];

            // Modified: frontmatter key first, then latest git commit, then today
            var modified = fm.Modified
                           ?? (history.Count > 0 ? history[^1] : null)
                           ?? DateTime.UtcNow.ToString("yyyy-MM-dd");

            // If the vault has no git commits yet (fresh clone / local dev), fall back to
            // the frontmatter modified date so the heatmap shows at least one entry per note.
            var effectiveHistory = history.Count > 0
                ? history
                : fm.Modified is not null ? (IReadOnlyList<string>)[fm.Modified] : [];

            realNodes.Add(new RealGraphNode(
                Id: note.Id,
                Title: fm.Title,
                Path: note.RelativePath.Replace('\\', '/'),
                Category: fm.Category,
                Level: fm.Level,
                Status: fm.Status,
                Tags: fm.Tags,
                Aliases: fm.Aliases,
                Modified: modified,
                Excerpt: ComputeExcerpt(note.BodyMarkdown),
                WordCount: ComputeWordCount(note.BodyMarkdown),
                History: effectiveHistory,
                NoteType: fm.NoteType
            ));
        }

        // ── 2. Ghost nodes ────────────────────────────────────────────────────
        // Group ghost links by normalised ghost id.
        var ghostGroups = new Dictionary<string, (string FirstTitle, List<string> Sources)>(
            StringComparer.Ordinal);

        // Track first-seen title per ghost id
        var ghostTitles = new Dictionary<string, string>(StringComparer.Ordinal);

        foreach (var link in links.Where(l => l.IsGhost))
        {
            var ghostId = LinkResolver.NormalizeGhostId(link.RawTarget);

            ghostTitles.TryAdd(ghostId, link.RawTarget);

            if (!ghostGroups.TryGetValue(ghostId, out var group))
            {
                ghostGroups[ghostId] = (link.RawTarget, [link.SourceId]);
            }
            else
            {
                if (!group.Sources.Contains(link.SourceId))
                    group.Sources.Add(link.SourceId);
            }
        }

        var ghostNodes = ghostGroups.Select(kvp => (GraphNode)new GhostGraphNode(
            Id: kvp.Key,
            Title: ghostTitles.TryGetValue(kvp.Key, out var t) ? t : kvp.Key,
            ReferencedBy: kvp.Value.Sources,
            ReferenceCount: kvp.Value.Sources.Count
        )).ToList();

        // ── 3. Edges ──────────────────────────────────────────────────────────
        // Build a map of normalised ghost id → ghost id (for edge target)
        var ghostIdByNorm = ghostGroups.Keys.ToDictionary(k => k, k => k);

        var edges = new List<GraphEdge>(links.Count);
        foreach (var link in links)
        {
            var targetId = link.IsGhost
                ? LinkResolver.NormalizeGhostId(link.RawTarget)
                : link.TargetId!;

            edges.Add(new GraphEdge(
                link.SourceId, targetId, link.LinkText, link.Kind, link.Confidence));
        }

        // ── 4. Assemble graph ─────────────────────────────────────────────────
        var allNodes = new List<GraphNode>(realNodes.Count + ghostNodes.Count);
        allNodes.AddRange(realNodes);
        allNodes.AddRange(ghostNodes);

        return new KnowledgeGraph
        {
            Nodes = allNodes,
            Edges = edges,
            Warnings = warnings
        };
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static string ComputeExcerpt(string body)
    {
        // Strip markdown syntax characters, then normalise whitespace
        var stripped = MarkdownChars.Replace(body, " ");
        stripped = MultiSpace.Replace(stripped, " ").Trim();

        return stripped.Length <= 200
            ? stripped
            : stripped[..200].TrimEnd();
    }

    private static int ComputeWordCount(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return 0;

        return body.Split(WhitespaceSeparators, StringSplitOptions.RemoveEmptyEntries).Length;
    }
}

using System.Text.RegularExpressions;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;

namespace Synapse.Generator.Domain.Resolution;

/// <summary>
/// Resolves [[wikilinks]] AND typed frontmatter relations across a set of notes, using three tiers:
/// 1. Full relative-path match (e.g. "subdir/note.md")
/// 2. Case-insensitive stem (filename without extension) match
/// 3. Case-insensitive alias match (from mapped frontmatter)
///
/// Unresolved links become ghost entries.
/// Multiple candidates within the same tier emit an <see cref="Warning"/>.
///
/// Typed relations (frontmatter <c>relations:</c>) go through exactly the same tiers, so a
/// relation pointing outside the vault becomes a ghost node like any other dangling link —
/// it is visible rather than silently dropped.
/// </summary>
public class LinkResolver : ILinkResolver
{
    private static readonly Regex CollapseWhitespace = new(@"\s+", RegexOptions.Compiled);

    /// <inheritdoc />
    public (IReadOnlyList<ResolvedLink> Links, IReadOnlyList<Warning> Warnings) Resolve(
        IReadOnlyList<RawNote> notes,
        IReadOnlyDictionary<string, MappedFrontmatter> frontmatters)
    {
        var warnings = new List<Warning>();

        // Build Tier-1: RelativePath → Id (normalised path separator)
        // Build Tier-2: stem (lower) → list of ids
        // Build Tier-3: alias (lower) → list of ids
        var pathToId = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var stemToIds = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        var aliasToIds = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);

        foreach (var note in notes)
        {
            // Tier 1 — relative path (forward-slash normalised)
            var normPath = note.RelativePath.Replace('\\', '/');
            pathToId.TryAdd(normPath, note.Id);

            // Tier 2 — stem (id is already the stem)
            if (!stemToIds.TryGetValue(note.Id, out var stemList))
                stemToIds[note.Id] = stemList = [];
            stemList.Add(note.Id);

            // Warn on duplicate id (different files with same stem)
            if (stemList.Count == 2)
                warnings.Add(new Warning("duplicate-id", note.Id, note.Id, null));

            // Tier 3 — aliases from mapped frontmatter
            if (frontmatters.TryGetValue(note.Id, out var fm))
            {
                foreach (var alias in fm.Aliases)
                {
                    if (!aliasToIds.TryGetValue(alias, out var aliasList))
                        aliasToIds[alias] = aliasList = [];
                    aliasList.Add(note.Id);
                }
            }
        }

        var links = new List<ResolvedLink>();

        foreach (var note in notes)
        {
            foreach (var wikiLink in note.WikiLinks)
            {
                var target = wikiLink.Target;
                if (target is null)
                {
                    // Heading-only link (no target) — skip
                    continue;
                }

                var resolved = TryResolve(
                    note.Id, target, wikiLink.RawText, target,
                    pathToId, stemToIds, aliasToIds,
                    warnings);

                links.Add(resolved);
            }

            // Typed relations declared in frontmatter — same resolution, different edge kind.
            if (!frontmatters.TryGetValue(note.Id, out var noteFrontmatter))
                continue;

            foreach (var relation in noteFrontmatter.Relations ?? [])
            {
                if (string.IsNullOrWhiteSpace(relation.Target))
                    continue;

                var resolved = TryResolve(
                    note.Id, relation.Target, relation.Target, relation.Target,
                    pathToId, stemToIds, aliasToIds,
                    warnings);

                links.Add(resolved with { Kind = relation.Kind, Confidence = relation.Confidence });
            }
        }

        return (links, warnings);
    }

    private static ResolvedLink TryResolve(
        string sourceId,
        string target,
        string rawText,
        string rawTarget,
        Dictionary<string, string> pathToId,
        Dictionary<string, List<string>> stemToIds,
        Dictionary<string, List<string>> aliasToIds,
        List<Warning> warnings)
    {
        // Tier 1: full relative-path match
        // Normalise: ensure ".md" suffix
        var pathTarget = target.EndsWith(".md", StringComparison.OrdinalIgnoreCase)
            ? target
            : target + ".md";
        pathTarget = pathTarget.Replace('\\', '/');

        if (pathToId.TryGetValue(pathTarget, out var pathMatch))
            return new ResolvedLink(sourceId, pathMatch, rawText, false, rawTarget);

        // Tier 2: case-insensitive stem match
        if (stemToIds.TryGetValue(target, out var stemMatches) && stemMatches.Count > 0)
        {
            if (stemMatches.Count > 1)
                warnings.Add(new Warning("ambiguous-link", sourceId, rawText, stemMatches[0]));
            return new ResolvedLink(sourceId, stemMatches[0], rawText, false, rawTarget);
        }

        // Tier 3: case-insensitive alias match
        if (aliasToIds.TryGetValue(target, out var aliasMatches) && aliasMatches.Count > 0)
        {
            if (aliasMatches.Count > 1)
                warnings.Add(new Warning("ambiguous-link", sourceId, rawText, aliasMatches[0]));
            return new ResolvedLink(sourceId, aliasMatches[0], rawText, false, rawTarget);
        }

        // Unresolved → ghost
        return new ResolvedLink(sourceId, null, rawText, true, rawTarget);
    }

    /// <summary>
    /// Normalises a raw link target into a stable ghost id:
    /// trim, collapse internal whitespace, lowercase.
    /// </summary>
    public static string NormalizeGhostId(string target) =>
        CollapseWhitespace.Replace(target.Trim(), " ").ToLowerInvariant();
}

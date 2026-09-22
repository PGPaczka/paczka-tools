using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;

namespace Synapse.Generator.Domain.Resolution;

public interface ILinkResolver
{
    /// <summary>
    /// Resolves all wikilinks in <paramref name="notes"/> to concrete note IDs (or ghost markers).
    /// Pure — no IO.
    /// </summary>
    (IReadOnlyList<ResolvedLink> Links, IReadOnlyList<Warning> Warnings) Resolve(
        IReadOnlyList<RawNote> notes,
        IReadOnlyDictionary<string, MappedFrontmatter> frontmatters);
}

namespace Synapse.Generator.Domain.Mapping;

/// <summary>
/// One typed relation declared in a note's frontmatter, e.g.
/// <code>
/// relations:
///   - target: docker-basics
///     kind: near_duplicate
///     confidence: 0.78
/// </code>
/// <paramref name="Target"/> is resolved through the same tiers as a wikilink, so an
/// unresolved target becomes a ghost node instead of being dropped.
/// </summary>
public record FrontmatterRelation(string Target, string Kind, double? Confidence = null);

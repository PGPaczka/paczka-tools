namespace Synapse.Generator.Domain.Graph;

/// <summary>
/// A directed edge. <paramref name="Kind"/> says WHY the two notes are connected:
/// <c>link</c> for a plain [[wikilink]], or whatever a typed frontmatter relation declared
/// (e.g. <c>near_duplicate</c>, <c>older_version</c>, <c>contains</c>). Kept free-form so a
/// vault can define its own vocabulary; the viewer styles whatever it finds.
/// </summary>
public record GraphEdge(
    string Source,
    string Target,
    string LinkText,
    string Kind = EdgeKinds.Link,
    double? Confidence = null
);

/// <summary>Kinds the generator itself produces. A vault may declare others.</summary>
public static class EdgeKinds
{
    /// <summary>A plain [[wikilink]] found in the note body.</summary>
    public const string Link = "link";
}

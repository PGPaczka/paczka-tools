namespace Synapse.Generator.Domain.Resolution;

public record ResolvedLink(
    string SourceId,
    string? TargetId,   // null = unresolved (ghost)
    string LinkText,    // raw wikilink text including |alias and #heading
    bool IsGhost,
    string RawTarget,   // WikiLinkRef.Target text used for resolution (for ghost id normalisation)
    string Kind = Domain.Graph.EdgeKinds.Link,  // why the two notes are connected
    double? Confidence = null                   // optional strength, carried from typed relations
);

namespace Synapse.Generator.Domain.Graph;

/// <summary>Discriminated-union base for graph nodes.</summary>
public abstract record GraphNode(string Id);

/// <summary>A note that exists on disk.</summary>
/// <remarks>
/// <c>NoteType</c> is the vault's own taxonomy of what a note IS (e.g. "semester", "subject",
/// "file") and is serialised as <c>type</c>. It is deliberately separate from the <c>kind</c>
/// discriminator, which only says real-vs-ghost, and free-form, so a vault is not limited to
/// a taxonomy this generator happens to know.
/// </remarks>
public sealed record RealGraphNode(
    string Id,
    string Title,
    string Path,
    string Category,
    int? Level,
    string? Status,
    IReadOnlyList<string> Tags,
    IReadOnlyList<string> Aliases,
    string Modified,
    string Excerpt,
    int WordCount,
    IReadOnlyList<string> History,
    string? NoteType = null
) : GraphNode(Id);

/// <summary>A note referenced by wikilinks but not found on disk.</summary>
public sealed record GhostGraphNode(
    string Id,
    string Title,
    List<string> ReferencedBy,
    int ReferenceCount
) : GraphNode(Id);

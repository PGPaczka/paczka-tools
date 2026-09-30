namespace Synapse.Generator.Domain.Mapping;

public record MappedFrontmatter(
    string Title,
    string Category,
    int? Level,
    string? Status,
    IReadOnlyList<string> Tags,
    IReadOnlyList<string> Aliases,
    string? Modified,
    // Free-form node type (e.g. "semester", "subject", "file"). Null when the key is absent.
    // Deliberately not an enum: a vault decides its own taxonomy, the generator only carries it.
    string? NoteType = null,
    // Typed relations declared in frontmatter — edges that are NOT plain [[wikilinks]].
    IReadOnlyList<FrontmatterRelation>? Relations = null,
    // What CONTENT this note stands for, when it stands for one: its hash, its size in
    // bytes and what kind of thing it is. Null for ordinary notes, which are their own
    // content. SizeBytes is long because media files pass what an int can hold.
    string? Sha256 = null,
    long? SizeBytes = null,
    string? ContentKind = null
);

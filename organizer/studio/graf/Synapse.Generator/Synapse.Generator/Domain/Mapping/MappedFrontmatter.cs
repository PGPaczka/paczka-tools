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
    IReadOnlyList<FrontmatterRelation>? Relations = null
);

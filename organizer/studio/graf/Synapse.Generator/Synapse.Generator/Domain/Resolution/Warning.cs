namespace Synapse.Generator.Domain.Resolution;

/// <summary>
/// A non-fatal concern surfaced during link resolution (ambiguous or duplicate).
/// </summary>
public record Warning(
    string Kind,        // "ambiguous-link" | "duplicate-id"
    string NoteId,
    string LinkText,
    string? ResolvedTo
);

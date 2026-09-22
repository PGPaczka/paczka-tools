namespace Synapse.Generator.Domain.Links;

/// <summary>
/// Represents a parsed [[wikilink]] reference from a note's markdown body.
/// Parsing rule: [[Target#Heading|Alias]]
/// </summary>
public record WikiLinkRef(
    string RawText,
    string? Target,
    string? Heading,
    string? Alias
);

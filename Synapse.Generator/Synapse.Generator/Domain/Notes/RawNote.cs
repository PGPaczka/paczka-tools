using Synapse.Generator.Domain.Links;

namespace Synapse.Generator.Domain.Notes;

/// <summary>
/// A note as read from disk — frontmatter parsed, wikilinks extracted, body preserved as raw markdown.
/// </summary>
public record RawNote(
    string Id,
    string RelativePath,
    Dictionary<string, object?> Frontmatter,
    IReadOnlyList<WikiLinkRef> WikiLinks,
    string BodyMarkdown
);

namespace Synapse.Generator.Parsing;

/// <summary>
/// Provides structural information about a markdown document needed by downstream extractors.
/// </summary>
public interface IMarkdownParser
{
    /// <summary>
    /// Returns the (inclusive) character-offset ranges of every fenced code block in
    /// <paramref name="markdown"/>. Ranges are used by <see cref="WikiLinkExtractor"/>
    /// to skip <c>[[wikilinks]]</c> that appear inside code blocks.
    /// </summary>
    IReadOnlyList<(int Start, int End)> GetFencedCodeBlockRanges(string markdown);
}

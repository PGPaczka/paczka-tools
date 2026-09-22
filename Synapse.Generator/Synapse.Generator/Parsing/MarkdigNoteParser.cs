using Markdig;
using Markdig.Syntax;

namespace Synapse.Generator.Parsing;

/// <summary>
/// Uses the Markdig AST to locate fenced code block spans within raw markdown.
/// </summary>
public class MarkdigNoteParser : IMarkdownParser
{
    private static readonly MarkdownPipeline Pipeline =
        new MarkdownPipelineBuilder().Build();

    /// <inheritdoc />
    public IReadOnlyList<(int Start, int End)> GetFencedCodeBlockRanges(string markdown)
    {
        var document = Markdown.Parse(markdown, Pipeline);

        return document
            .Descendants<FencedCodeBlock>()
            .Select(b => (b.Span.Start, b.Span.End))
            .ToList();
    }
}

using System.Text.RegularExpressions;
using Synapse.Generator.Domain.Links;

namespace Synapse.Generator.Parsing;

/// <summary>
/// Extracts [[wikilink]] references from raw markdown, excluding any links that
/// appear inside fenced code blocks (as identified by <see cref="IMarkdownParser"/>).
/// </summary>
public class WikiLinkExtractor
{
    // Matches [[anything except ]]] — handles Target#Heading|Alias combinations.
    private static readonly Regex WikiLinkPattern =
        new(@"\[\[([^\]]+)\]\]", RegexOptions.Compiled);

    private readonly IMarkdownParser _parser;

    public WikiLinkExtractor(IMarkdownParser parser)
    {
        _parser = parser;
    }

    /// <summary>
    /// Parses all <c>[[wikilinks]]</c> from <paramref name="markdown"/>,
    /// skipping links whose character position falls within a fenced code block.
    /// </summary>
    public List<WikiLinkRef> Extract(string markdown)
    {
        var codeRanges = _parser.GetFencedCodeBlockRanges(markdown);
        var results = new List<WikiLinkRef>();

        foreach (Match match in WikiLinkPattern.Matches(markdown))
        {
            // Skip if the match start is inside any fenced code block span.
            if (codeRanges.Any(r => match.Index >= r.Start && match.Index <= r.End))
                continue;

            var inner = match.Groups[1].Value;

            // Split on '|' first to extract optional display/alias text.
            string? alias = null;
            var targetAndHeading = inner;

            var pipeIdx = inner.IndexOf('|');
            if (pipeIdx >= 0)
            {
                targetAndHeading = inner[..pipeIdx];
                alias = NullIfEmpty(inner[(pipeIdx + 1)..]);
            }

            // Split on '#' to extract optional heading anchor.
            string? target;
            string? heading = null;

            var hashIdx = targetAndHeading.IndexOf('#');
            if (hashIdx >= 0)
            {
                target = NullIfEmpty(targetAndHeading[..hashIdx].Trim());
                heading = NullIfEmpty(targetAndHeading[(hashIdx + 1)..].Trim());
            }
            else
            {
                target = NullIfEmpty(targetAndHeading.Trim());
            }

            results.Add(new WikiLinkRef(match.Value, target, heading, alias));
        }

        return results;
    }

    private static string? NullIfEmpty(string s) =>
        string.IsNullOrEmpty(s) ? null : s;
}

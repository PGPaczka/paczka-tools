namespace Synapse.Generator.Parsing;

/// <summary>
/// Parses the YAML front-matter block from a markdown file.
/// </summary>
public interface IFrontmatterReader
{
    /// <summary>
    /// Extracts the leading ---…--- YAML block from <paramref name="fullMarkdown"/>
    /// and deserialises it into a key/value dictionary.
    /// Returns an empty dictionary if no valid front-matter is found.
    /// Never throws.
    /// </summary>
    Dictionary<string, object?> Read(string fullMarkdown);
}

using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Synapse.Generator.Parsing;

/// <summary>
/// Reads the leading YAML front-matter block delimited by triple-dash fences (---).
/// </summary>
public class YamlFrontmatterReader : IFrontmatterReader
{
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(NullNamingConvention.Instance)
        .Build();

    /// <inheritdoc />
    public Dictionary<string, object?> Read(string fullMarkdown)
    {
        // Must start exactly with "---" on the first line.
        if (!fullMarkdown.StartsWith("---", StringComparison.Ordinal))
            return new Dictionary<string, object?>();

        // Skip the opening "---" line.
        var afterOpenFence = fullMarkdown.IndexOf('\n');
        if (afterOpenFence < 0)
            return new Dictionary<string, object?>();

        afterOpenFence += 1; // position of first character after the newline

        // Find the closing "---" fence — it must appear at the start of a line.
        var closeFencePos = fullMarkdown.IndexOf("\n---", afterOpenFence, StringComparison.Ordinal);
        if (closeFencePos < 0)
            return new Dictionary<string, object?>();

        var yamlBlock = fullMarkdown[afterOpenFence..closeFencePos];

        if (string.IsNullOrWhiteSpace(yamlBlock))
            return new Dictionary<string, object?>();

        try
        {
            var result = Deserializer.Deserialize<Dictionary<string, object?>>(yamlBlock);
            return result ?? new Dictionary<string, object?>();
        }
        catch
        {
            return new Dictionary<string, object?>();
        }
    }
}

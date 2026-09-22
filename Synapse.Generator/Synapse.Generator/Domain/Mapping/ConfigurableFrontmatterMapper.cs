using Synapse.Generator.Configuration;

namespace Synapse.Generator.Domain.Mapping;

/// <summary>
/// Maps a raw YAML frontmatter dictionary to a strongly-typed <see cref="MappedFrontmatter"/> record
/// using configurable key names and sensible defaults.
/// </summary>
public class ConfigurableFrontmatterMapper : IFrontmatterMapper
{
    private static readonly HashSet<string> ValidStatuses =
        new(StringComparer.OrdinalIgnoreCase) { "not-started", "in-progress", "completed" };

    /// <summary>Kind used when a relation entry does not declare one.</summary>
    public const string DefaultRelationKind = "related";

    private readonly FrontmatterMapConfig _config;

    public ConfigurableFrontmatterMapper(FrontmatterMapConfig config)
    {
        _config = config;
    }

    /// <inheritdoc />
    public MappedFrontmatter Map(Dictionary<string, object?> frontmatter, string fileName)
    {
        var title = GetString(frontmatter, _config.TitleKey)
                    ?? Path.GetFileNameWithoutExtension(fileName);

        var category = GetString(frontmatter, _config.CategoryKey) ?? "Uncategorized";
        var level = GetInt(frontmatter, _config.LevelKey);
        var status = NormalizeStatus(GetString(frontmatter, _config.StatusKey));
        var tags = GetList(frontmatter, _config.TagsKey);
        var aliases = GetList(frontmatter, _config.AliasesKey);
        var modified = GetString(frontmatter, _config.ModifiedKey);
        var noteType = GetString(frontmatter, _config.TypeKey);
        var relations = GetRelations(frontmatter, _config.RelationsKey);

        return new MappedFrontmatter(
            title, category, level, status, tags, aliases, modified, noteType, relations);
    }

    /// <summary>
    /// Reads typed relations from a YAML sequence of mappings:
    /// <code>
    /// relations:
    ///   - target: docker-basics
    ///     kind: near_duplicate
    ///     confidence: 0.78
    /// </code>
    /// A bare string entry (<c>relations: [docker-basics]</c>) is accepted too and defaults to
    /// <see cref="DefaultRelationKind"/>. An entry without a target is skipped rather than
    /// failing the run — vault hygiene never breaks generation, same policy as warnings.
    /// </summary>
    /// <remarks>
    /// YamlDotNet deserialises a sequence of mappings as <c>List&lt;object&gt;</c> holding
    /// <c>Dictionary&lt;object, object&gt;</c>, which is why this cannot reuse <see cref="GetList"/>:
    /// that one calls <c>ToString()</c> on every element and would yield type names.
    /// </remarks>
    private static IReadOnlyList<FrontmatterRelation> GetRelations(
        Dictionary<string, object?> frontmatter, string key)
    {
        if (!frontmatter.TryGetValue(key, out var value) || value is null)
            return [];

        var entries = value is List<object> list ? list : [value];
        var relations = new List<FrontmatterRelation>(entries.Count);

        foreach (var entry in entries)
        {
            switch (entry)
            {
                case IDictionary<object, object> map:
                {
                    var target = MapValue(map, "target") ?? MapValue(map, "id");
                    if (string.IsNullOrWhiteSpace(target))
                        continue;

                    var kind = MapValue(map, "kind") ?? MapValue(map, "type") ?? DefaultRelationKind;
                    var confidence = double.TryParse(
                        MapValue(map, "confidence"),
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture,
                        out var parsed)
                        ? parsed
                        : (double?)null;

                    relations.Add(new FrontmatterRelation(target.Trim(), kind.Trim(), confidence));
                    break;
                }

                case string scalar when scalar.Trim().Length > 0:
                    relations.Add(new FrontmatterRelation(scalar.Trim(), DefaultRelationKind));
                    break;
            }
        }

        return relations;
    }

    private static string? MapValue(IDictionary<object, object> map, string key)
    {
        foreach (var pair in map)
        {
            if (string.Equals(pair.Key?.ToString(), key, StringComparison.OrdinalIgnoreCase))
                return pair.Value?.ToString();
        }

        return null;
    }

    private static string? GetString(Dictionary<string, object?> frontmatter, string key)
    {
        if (!frontmatter.TryGetValue(key, out var value) || value is null)
            return null;

        var s = value.ToString()?.Trim();
        return string.IsNullOrEmpty(s) ? null : s;
    }

    private static int? GetInt(Dictionary<string, object?> frontmatter, string key)
    {
        if (!frontmatter.TryGetValue(key, out var value) || value is null)
            return null;

        return int.TryParse(value.ToString(), out var result) ? result : null;
    }

    private static IReadOnlyList<string> GetList(Dictionary<string, object?> frontmatter, string key)
    {
        if (!frontmatter.TryGetValue(key, out var value) || value is null)
            return [];

        return value switch
        {
            // YAML sequence deserialized as List<object>
            List<object> list => list
                .Select(x => x.ToString()?.Trim() ?? string.Empty)
                .Where(x => x.Length > 0)
                .ToList(),

            // Scalar string — may be comma-separated
            string s => s.Split(',', StringSplitOptions.RemoveEmptyEntries)
                .Select(x => x.Trim())
                .Where(x => x.Length > 0)
                .ToList(),

            // Any other scalar: treat as single-element list
            _ => value.ToString() is { Length: > 0 } str
                ? [str.Trim()]
                : []
        };
    }

    private static string? NormalizeStatus(string? status)
    {
        if (status is null)
            return null;

        var normalized = status.Trim().ToLowerInvariant();
        return ValidStatuses.Contains(normalized) ? normalized : null;
    }
}

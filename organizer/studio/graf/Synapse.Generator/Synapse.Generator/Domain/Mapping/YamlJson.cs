using System.Globalization;
using System.Text.Json.Nodes;

namespace Synapse.Generator.Domain.Mapping;

/// <summary>
/// Turns a YAML value that YamlDotNet handed back into a <see cref="JsonNode"/>.
/// </summary>
/// <remarks>
/// A vault may declare a whole block of structured data — a course package writes one
/// describing the file a note stands for — and the generator carries it through to
/// graph.json without knowing its shape. That is deliberate: the shape is the vault's
/// business and will change more often than this code should.
///
/// Types survive because the reader is configured to type unquoted scalars
/// (<c>WithAttemptingUnquotedStringTypeDeserialization</c>): a vault quotes the strings
/// it means as strings, so a folder named <c>true</c> stays a string while
/// <c>confidence: 0.9</c> arrives as a number. Nothing here guesses from text.
/// </remarks>
public static class YamlJson
{
    /// <summary>Maximum nesting carried across; deeper levels are dropped.</summary>
    private const int MaxDepth = 12;

    public static JsonNode? Convert(object? value) => Convert(value, 0);

    private static JsonNode? Convert(object? value, int depth)
    {
        if (value is null || depth > MaxDepth)
            return null;

        switch (value)
        {
            case IDictionary<object, object> map:
            {
                var obj = new JsonObject();
                foreach (var pair in map)
                {
                    var key = pair.Key?.ToString();
                    if (string.IsNullOrEmpty(key))
                        continue;
                    var child = Convert(pair.Value, depth + 1);
                    if (child is not null)
                        obj[key] = child;
                }
                return obj.Count > 0 ? obj : null;
            }

            case IEnumerable<object> list when value is not string:
            {
                var arr = new JsonArray();
                foreach (var item in list)
                {
                    var child = Convert(item, depth + 1);
                    if (child is not null)
                        arr.Add(child);
                }
                return arr.Count > 0 ? arr : null;
            }

            case bool flag:
                return JsonValue.Create(flag);

            case int or long or short or byte:
                return JsonValue.Create(System.Convert.ToInt64(value, CultureInfo.InvariantCulture));

            // A YAML scalar like `0.9` is parsed as a float, and widening a float to a
            // double keeps the single-precision error: 0.9 becomes 0.8999999761581421 in
            // the output. Going through the round-trip text form restores what was written.
            case float single:
                return JsonValue.Create(double.Parse(
                    single.ToString("R", CultureInfo.InvariantCulture), CultureInfo.InvariantCulture));

            case double or decimal:
                return JsonValue.Create(System.Convert.ToDouble(value, CultureInfo.InvariantCulture));

            default:
                return JsonValue.Create(value.ToString());
        }
    }
}

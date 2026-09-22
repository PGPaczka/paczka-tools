using System.Text.Json;
using System.Text.Json.Nodes;
using Synapse.Generator.Domain.Notes;

namespace Synapse.Generator.Serialization;

/// <summary>
/// Serialises the full-text search index to search-index.json.
/// Format: JSON array of { id, title, body } — one entry per real note.
/// Written compact (no indentation) since it's loaded once and parsed in bulk.
/// </summary>
public class SearchIndexSerializer
{
    private static readonly JsonSerializerOptions WriteOptions = new()
    {
        WriteIndented = false,
        TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver()
    };

    public string Serialize(IReadOnlyList<RawNote> rawNotes, IReadOnlyDictionary<string, string> titleById)
    {
        var arr = new JsonArray();
        foreach (var note in rawNotes.OrderBy(n => n.Id, StringComparer.Ordinal))
        {
            if (!titleById.TryGetValue(note.Id, out var title)) continue;
            arr.Add(new JsonObject
            {
                ["id"]    = note.Id,
                ["title"] = title,
                ["body"]  = note.BodyMarkdown,
            });
        }
        return arr.ToJsonString(WriteOptions);
    }

    /// <summary>Atomic write: temp file → rename, same as <see cref="JsonGraphSerializer"/>.</summary>
    public void WriteAtomic(string outputPath, string json)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(outputPath))!;
        Directory.CreateDirectory(dir);

        var tmp = Path.Combine(dir, $".search-{Guid.NewGuid():N}.tmp");
        try
        {
            File.WriteAllText(tmp, json);
            File.Move(tmp, outputPath, overwrite: true);
        }
        catch
        {
            try { File.Delete(tmp); } catch { /* best-effort */ }
            throw;
        }
    }
}

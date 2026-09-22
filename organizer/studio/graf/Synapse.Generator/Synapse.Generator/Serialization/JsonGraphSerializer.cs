using System.Text.Json;
using System.Text.Json.Nodes;
using Synapse.Generator.Domain.Graph;
using Synapse.Generator.Domain.Resolution;

namespace Synapse.Generator.Serialization;

/// <summary>
/// Serialises a <see cref="KnowledgeGraph"/> to the graph.json schema (v1).
/// Uses System.Text.Json.Nodes for manual JSON construction — deterministic ordering,
/// trim-compatible (no generic serializer reflection).
/// </summary>
public class JsonGraphSerializer
{
    /// <summary>
    /// Bumped to 2 when nodes gained <c>type</c> and edges gained <c>kind</c>/<c>confidence</c>.
    /// The viewer hard-equality-checks this; there is no migration machinery by design —
    /// regenerating the graph takes seconds.
    /// </summary>
    public const int SchemaVersion = 2;

    private static readonly JsonSerializerOptions WriteOptions = new()
    {
        WriteIndented = true,
        TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver()
    };

    /// <summary>
    /// Produces the graph.json JSON string from <paramref name="graph"/>.
    /// Nodes sorted by id; edges sorted by (source, target); warnings sorted by (noteId, linkText).
    /// </summary>
    public string Serialize(KnowledgeGraph graph, string vaultName, string generatedAt)
    {
        var orphanIds = graph.OrphanIds();
        var realNodes = graph.Nodes.OfType<RealGraphNode>().ToList();
        var ghostNodes = graph.Nodes.OfType<GhostGraphNode>().ToList();

        // ── Vault metadata ────────────────────────────────────────────────────
        var vault = new JsonObject
        {
            ["name"]        = vaultName,
            ["notesCount"]  = realNodes.Count,
            ["ghostCount"]  = ghostNodes.Count,
            ["orphanCount"] = orphanIds.Count
        };

        // ── Nodes (sorted by id) ──────────────────────────────────────────────
        var nodesArray = new JsonArray();
        foreach (var node in graph.Nodes.OrderBy(n => n.Id, StringComparer.Ordinal))
        {
            nodesArray.Add(node is RealGraphNode real
                ? SerializeReal(real)
                : SerializeGhost((GhostGraphNode)node));
        }

        // ── Edges (sorted by source, then target) ─────────────────────────────
        var edgesArray = new JsonArray();
        foreach (var edge in graph.Edges
                     .OrderBy(e => e.Source, StringComparer.Ordinal)
                     .ThenBy(e => e.Target, StringComparer.Ordinal))
        {
            var edgeObj = new JsonObject
            {
                ["source"]   = edge.Source,
                ["target"]   = edge.Target,
                ["linkText"] = edge.LinkText,
                ["kind"]     = edge.Kind
            };

            // confidence: only when the vault declared one (schema allows absence)
            if (edge.Confidence.HasValue)
                edgeObj["confidence"] = JsonValue.Create(edge.Confidence.Value);

            edgesArray.Add(edgeObj);
        }

        // ── Warnings (sorted by noteId, then linkText) ────────────────────────
        var warningsArray = new JsonArray();
        foreach (var w in graph.Warnings
                     .OrderBy(w => w.NoteId, StringComparer.Ordinal)
                     .ThenBy(w => w.LinkText, StringComparer.Ordinal))
        {
            warningsArray.Add(SerializeWarning(w));
        }

        // ── Root object ───────────────────────────────────────────────────────
        var root = new JsonObject
        {
            ["schemaVersion"] = SchemaVersion,
            ["generatedAt"]   = generatedAt,
            ["vault"]         = vault,
            ["nodes"]         = nodesArray,
            ["edges"]         = edgesArray,
            ["warnings"]      = warningsArray
        };

        return root.ToJsonString(WriteOptions);
    }

    /// <summary>
    /// Writes <paramref name="json"/> to <paramref name="outputPath"/> atomically:
    /// writes to a temp file first, then renames over the destination.
    /// </summary>
    public void WriteAtomic(string outputPath, string json)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(outputPath))!;
        Directory.CreateDirectory(dir);

        var tmp = Path.Combine(dir, $".graph-{Guid.NewGuid():N}.tmp");
        try
        {
            File.WriteAllText(tmp, json);
            File.Move(tmp, outputPath, overwrite: true);
        }
        catch
        {
            // Clean up temp file on failure
            try { File.Delete(tmp); } catch { /* best-effort */ }
            throw;
        }
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private static JsonObject SerializeReal(RealGraphNode node)
    {
        var obj = new JsonObject
        {
            ["id"]       = node.Id,
            ["kind"]     = "real",
            ["title"]    = node.Title,
            ["path"]     = node.Path,
            ["category"] = node.Category,
            ["level"]    = node.Level.HasValue ? JsonValue.Create(node.Level.Value) : null,
            ["status"]   = node.Status is not null ? JsonValue.Create(node.Status) : null,
            ["tags"]     = ToJsonArray(node.Tags),
            ["aliases"]  = ToJsonArray(node.Aliases),
            ["modified"] = node.Modified,
            ["excerpt"]  = node.Excerpt,
            ["wordCount"]= node.WordCount
        };

        // type: the vault's own taxonomy of what this note IS; absent when not declared
        if (node.NoteType is not null)
            obj["type"] = node.NoteType;

        // history: include only when non-empty (schema says "absent if no git history")
        if (node.History.Count > 0)
            obj["history"] = ToJsonArray(node.History);

        return obj;
    }

    private static JsonObject SerializeGhost(GhostGraphNode node) =>
        new()
        {
            ["id"]             = node.Id,
            ["kind"]           = "ghost",
            ["title"]          = node.Title,
            ["referencedBy"]   = ToJsonArray(node.ReferencedBy.OrderBy(x => x)),
            ["referenceCount"] = node.ReferenceCount
        };

    private static JsonObject SerializeWarning(Warning w)
    {
        var obj = new JsonObject
        {
            ["kind"]   = w.Kind,
            ["noteId"] = w.NoteId,
            ["linkText"] = w.LinkText
        };
        if (w.ResolvedTo is not null)
            obj["resolvedTo"] = w.ResolvedTo;
        return obj;
    }

    private static JsonArray ToJsonArray(IEnumerable<string> items)
    {
        var arr = new JsonArray();
        foreach (var item in items)
            arr.Add(item);
        return arr;
    }
}

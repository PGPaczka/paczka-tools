using Synapse.Generator.Domain.Resolution;

namespace Synapse.Generator.Domain.Graph;

public class KnowledgeGraph
{
    public IReadOnlyList<GraphNode> Nodes { get; init; } = [];
    public IReadOnlyList<GraphEdge> Edges { get; init; } = [];
    public IReadOnlyList<Warning> Warnings { get; init; } = [];

    /// <summary>
    /// Builds an undirected adjacency map: node id → set of adjacent node ids (both directions).
    /// Only considers edges where both endpoints exist in <see cref="Nodes"/>.
    /// </summary>
    public Dictionary<string, HashSet<string>> Adjacency()
    {
        var adj = Nodes.ToDictionary(n => n.Id, _ => new HashSet<string>(StringComparer.Ordinal));

        foreach (var edge in Edges)
        {
            if (adj.TryGetValue(edge.Source, out var srcSet))
                srcSet.Add(edge.Target);

            if (adj.TryGetValue(edge.Target, out var tgtSet))
                tgtSet.Add(edge.Source);
        }

        return adj;
    }

    /// <summary>
    /// Returns the IDs of nodes that have no neighbours in either direction.
    /// </summary>
    public HashSet<string> OrphanIds()
    {
        var adj = Adjacency();
        var orphans = new HashSet<string>(StringComparer.Ordinal);

        foreach (var (id, neighbours) in adj)
        {
            if (neighbours.Count == 0)
                orphans.Add(id);
        }

        return orphans;
    }
}

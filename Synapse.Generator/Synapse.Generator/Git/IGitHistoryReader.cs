namespace Synapse.Generator.Git;

/// <summary>
/// Reads the commit history for a specific file within a git vault.
/// </summary>
public interface IGitHistoryReader
{
    /// <summary>
    /// Returns the commit dates for <paramref name="absoluteFilePath"/>, oldest first (yyyy-MM-dd).
    /// Returns an empty list if the file is untracked, the vault has no git repo, or git fails.
    /// Never throws.
    /// </summary>
    IReadOnlyList<string> GetHistory(string vaultRoot, string absoluteFilePath);
}

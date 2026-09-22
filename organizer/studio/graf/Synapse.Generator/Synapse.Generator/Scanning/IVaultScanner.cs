namespace Synapse.Generator.Scanning;

/// <summary>
/// Discovers markdown note files within a vault directory.
/// </summary>
public interface IVaultScanner
{
    /// <summary>
    /// Returns absolute paths to all *.md files in the vault, skipping hidden directories and dotfiles.
    /// </summary>
    IReadOnlyList<string> GetNoteFiles(string vaultRoot);
}

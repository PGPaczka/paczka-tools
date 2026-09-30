namespace Synapse.Generator.Tests.Helpers;

/// <summary>
/// The fixture vault as a repository of its own: a temp copy with one commit at a fixed date.
/// </summary>
/// <remarks>
/// Anything that asserts on <c>history</c> or on <c>modified</c> has to read those from a
/// repository, and reading them from the repository the tests happen to live in makes the
/// assertions mean different things in different checkouts. That is not hypothetical: when
/// this code was vendored into another project with <c>git subtree --squash</c>, the fixture
/// notes' history became a single commit dated by the merge, and with <c>--follow</c> it read
/// as no history at all — so <c>modified</c> fell back to TODAY and the golden file could
/// never match again.
///
/// The copy holds the same nine notes, committed once at <see cref="GitCommand.FixedDate"/>,
/// which is the date the golden file was recorded with.
/// </remarks>
internal static class FixtureVaultRepo
{
    private static readonly Lazy<string> _path = new(Create);

    public static string Path => _path.Value;

    public static string FilePath(string fileName) =>
        System.IO.Path.Combine(Path, fileName);

    private static string Create()
    {
        var root = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(), $"synapse-fixture-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);

        var source = FixtureVaultPath.GetPath();
        foreach (var file in Directory.EnumerateFiles(source, "*.md", SearchOption.AllDirectories))
        {
            var relative = System.IO.Path.GetRelativePath(source, file);
            var target = System.IO.Path.Combine(root, relative);
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }

        GitCommand.Run(root, "init", "-q", "-b", "main");
        GitCommand.Run(root, "add", "-A");
        GitCommand.Run(root, "commit", "-q", "-m", "fixture vault");

        return root;
    }
}

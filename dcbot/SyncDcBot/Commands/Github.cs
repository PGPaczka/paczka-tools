using Discord.Interactions;
using SyncDcBot.Repositories;
using SyncDcBot.Services;

namespace SyncDcBot.Commands;

public class GitHubModule(AddToRepoService github, CommandResultStore resultStore) : CommandBase(resultStore)
{
    [SlashCommand("dodaj-do-repo", "Adds user to Paczka github repo")]
    public async Task AddToRepoAsync(
        [Summary("profile", "Link to GitHub profile (eg. https://github.com/jankowalski)")]
        string profile)
    {
        if (!AddToRepoService.TryParseGitHubLogin(profile, out var ghUser))
        {
            ResultStore.SetFailure(Context.Interaction.Id, "Incorrect GitHub profile link.");
            return;
        }

        await DeferAsync(ephemeral: true);

        var result = await github.AddCollaboratorAsync(ghUser);
        ResultStore.Set(Context.Interaction.Id, result.ToCommandResult());
    }
}
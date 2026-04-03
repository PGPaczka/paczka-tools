using Discord.Interactions;
using Serilog.Events;
using SyncDcBot.Repositories;
using SyncDcBot.Services;

namespace SyncDcBot.Commands.Modules;

public class GitHubModule : CommandBase
{
    private readonly GitHubService _github;
    private readonly CommandResultStore _resultStore;

    public GitHubModule(GitHubService github, CommandResultStore resultStore)
    {
        _github = github;
        _resultStore = resultStore;
    }

    [SlashCommand("dodaj-do-repo", "Adds user to Paczka github repo")]
    public async Task AddToRepoAsync(
        [Summary("profil", "Link to GitHub profile (eg. https://github.com/jankowalski)")]
        string profile)
    {
        if (!GitHubService.TryParseGitHubLogin(profile, out var ghUser))
        {
            const string msg = "Incorrect GitHub profile link.";
            _resultStore.Set(Context.Interaction.Id, new CommandResult(false, msg, LogEventLevel.Warning));
            await RespondAsync($"{EmojiRepo.ErrorEmoji} {msg}", ephemeral: true);
            return;
        }

        await DeferAsync(ephemeral: true);

        var result = await _github.AddCollaboratorAsync(ghUser);
        _resultStore.Set(Context.Interaction.Id, new CommandResult(result.Success, result.Message, result.LogLevel));
        await FollowupAsync(result.Message, ephemeral: true);
    }
}
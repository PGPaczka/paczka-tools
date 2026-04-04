using Microsoft.Extensions.Configuration;
using Octokit;
using Serilog.Events;
using SyncDcBot.Repositories;

namespace SyncDcBot.Services;

public record PullRequestFetchResult(
    bool Success,
    string Message,
    LogEventLevel LogLevel,
    PullRequest? PullRequest = null)
{
    public static PullRequestFetchResult Ok(PullRequest pr) =>
        new(true, string.Empty, LogEventLevel.Debug, pr);

    public static PullRequestFetchResult Failure(string message, LogEventLevel level) =>
        new(false, message, level);

    public static implicit operator GitHubResult(PullRequestFetchResult r) =>
        new(r.Success, r.Message, r.LogLevel);
}

public class BypassPrRulesService
{
    private readonly GitHubClient _github;
    private readonly IConfiguration _config;

    public BypassPrRulesService(GitHubClient github, IConfiguration config)
    {
        _github = github;
        _config = config;
    }

    public async Task<GitHubResult> BypassMergePullRequestAsync(string prUrl)
    {
        var owner = _config["RepoOwner"];
        var repo = _config["RepoName"];

        var prParseResult = TryParsePullRequestNumber(prUrl, owner, repo, out var prNumber);
        if (!prParseResult.Success)
            return prParseResult;

        var prFetchResult = await FetchPullRequestAsync(owner, repo, prNumber);
        if (!prFetchResult.Success)
            return prFetchResult;

        var pr = prFetchResult.PullRequest!;

        var forcePushResult = await CheckForForcePushAsync(owner, repo, prNumber);
        if (!forcePushResult.Success)
            return forcePushResult;

        return await MergePullRequestAsync(owner, repo, pr);
    }

    private static GitHubResult TryParsePullRequestNumber(string prUrl, string owner, string repo, out int prNumber)
    {
        prNumber = 0;
        try
        {
            var uri = new Uri(prUrl.Trim());
            var expectedBase = $"github.com/{owner}/{repo}/pull/";

            if (!uri.AbsoluteUri.Contains(expectedBase))
                return new GitHubResult(false,
                    $"{EmojiRepo.ErrorEmoji} Invalid PR URL. Expected: `github.com/{owner}/{repo}/pull/[number]`",
                    LogEventLevel.Warning);

            var segment = uri.Segments.LastOrDefault()?.Trim('/');
            if (!int.TryParse(segment, out prNumber))
                return new GitHubResult(false,
                    $"{EmojiRepo.ErrorEmoji} Could not parse PR number from URL.",
                    LogEventLevel.Warning);

            return new GitHubResult(true, string.Empty, LogEventLevel.Debug);
        }
        catch
        {
            return new GitHubResult(false,
                $"{EmojiRepo.ErrorEmoji} Invalid URL format.",
                LogEventLevel.Warning);
        }
    }

    private async Task<PullRequestFetchResult> FetchPullRequestAsync(string owner, string repo, int prNumber)
    {
        try
        {
            var pr = await _github.PullRequest.Get(owner, repo, prNumber);

            if (pr.State.Value == ItemState.Closed)
                return PullRequestFetchResult.Failure(
                    $"{EmojiRepo.ErrorEmoji} PR #{prNumber} is already closed.",
                    LogEventLevel.Warning);

            if (pr.Merged)
                return PullRequestFetchResult.Failure(
                    $"{EmojiRepo.ErrorEmoji} PR #{prNumber} is already merged.",
                    LogEventLevel.Warning);

            return PullRequestFetchResult.Ok(pr);
        }
        catch (NotFoundException)
        {
            return PullRequestFetchResult.Failure(
                $"{EmojiRepo.ErrorEmoji} PR #{prNumber} not found.",
                LogEventLevel.Warning);
        }
    }

    private async Task<GitHubResult> CheckForForcePushAsync(string owner, string repo, int prNumber)
    {
        try
        {
            var events = await _github.Issue.Timeline.GetAllForIssue(owner, repo, prNumber);
            var hasForcePush = events.Any(e => e.Event.Value == EventInfoState.HeadRefForcePushed);

            if (hasForcePush)
                return new GitHubResult(false,
                    $"{EmojiRepo.ErrorEmoji} PR #{prNumber} contains a force push — merge blocked for safety.",
                    LogEventLevel.Warning);

            return new GitHubResult(true, string.Empty, LogEventLevel.Debug);
        }
        catch (Exception ex)
        {
            return new GitHubResult(false,
                $"{EmojiRepo.ErrorEmoji} Failed to fetch PR timeline: {ex.Message}",
                LogEventLevel.Error);
        }
    }

    private async Task<GitHubResult> MergePullRequestAsync(string owner, string repo, PullRequest pr)
    {
        try
        {
            await _github.PullRequest.Merge(owner, repo, pr.Number, new MergePullRequest
            {
                CommitMessage = $"[bot] Admin bypass merge of PR #{pr.Number}: {pr.Title}",
                MergeMethod = PullRequestMergeMethod.Merge
            });

            return new GitHubResult(true,
                $"{EmojiRepo.SuccessEmoji} PR #{pr.Number} merged successfully.",
                LogEventLevel.Information);
        }
        catch (PullRequestNotMergeableException)
        {
            return new GitHubResult(false,
                $"{EmojiRepo.ErrorEmoji} PR #{pr.Number} is not mergeable (conflicts?).",
                LogEventLevel.Warning);
        }
        catch (Exception ex)
        {
            return new GitHubResult(false,
                $"{EmojiRepo.ErrorEmoji} Unexpected error during merge: {ex.Message}",
                LogEventLevel.Error);
        }
    }
}
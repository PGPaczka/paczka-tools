using Microsoft.Extensions.Configuration;
using Octokit;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Services.GitHub;

public class BypassPrRulesService
{
    private readonly GitHubClient _github;
    private readonly IConfiguration _config;

    public BypassPrRulesService(GitHubClient github, IConfiguration config)
    {
        _github = github;
        _config = config;
    }

    public async Task<ServiceResult<BypassMergeResultType>> BypassMergePullRequestAsync(string prUrl)
    {
        var owner = _config["GitHubConfig:RepoOwner"]!;
        var repo = _config["GitHubConfig:RepoName"]!;

        var parseResult = TryParsePullRequestNumber(prUrl, owner, repo, out var prNumber);
        if (!parseResult.IsSuccess) return parseResult;

        var fetchResult = await FetchPullRequestAsync(owner, repo, prNumber);
        if (!fetchResult.IsSuccess) return fetchResult;

        var forcePushResult = await CheckForForcePushAsync(owner, repo, fetchResult.Data!);
        if (!forcePushResult.IsSuccess) return forcePushResult;

        var mergeResult = await MergePullRequestAsync(owner, repo, fetchResult.Data!);
        return mergeResult;
    }


    private static ServiceResult<BypassMergeResultType> TryParsePullRequestNumber(
        string prUrl, string owner, string repo, out int prNumber)
    {
        prNumber = 0;
        try
        {
            var uri = new Uri(prUrl.Trim());
            var expectedBase = $"github.com/{owner}/{repo}/pull/";

            if (!uri.AbsoluteUri.Contains(expectedBase))
            {
                return ServiceResult.Create(BypassMergeResultType.InvalidUrl,
                    $"Invalid PR URL. Expected: `github.com/{owner}/{repo}/pull/[number]`");
            }

            var segment = uri.Segments.LastOrDefault()?.Trim('/');
            if (!int.TryParse(segment, out prNumber))
            {
                return ServiceResult.Create(BypassMergeResultType.InvalidPrNumber);
            }

            return ServiceResult.Create(BypassMergeResultType.Success);
        }
        catch
        {
            return ServiceResult.Create(BypassMergeResultType.InvalidUrl, "Invalid URL format.");
        }
    }

    private async Task<ServiceResult<BypassMergeResultType, PullRequest>> FetchPullRequestAsync(
        string owner, string repo, int prNumber)
    {
        try
        {
            var pr = await _github.PullRequest.Get(owner, repo, prNumber);

            if (pr.State.Value == ItemState.Closed)
            {
                return ServiceResult.CreateWithDefault<BypassMergeResultType, PullRequest>(BypassMergeResultType
                    .AlreadyClosed);
            }

            if (pr.Merged)
            {
                return ServiceResult.CreateWithDefault<BypassMergeResultType, PullRequest>(BypassMergeResultType
                    .AlreadyMerged);
            }

            return ServiceResult.CreateWith(BypassMergeResultType.Success, pr);
        }
        catch (NotFoundException)
        {
            return ServiceResult.CreateWithDefault<BypassMergeResultType, PullRequest>(BypassMergeResultType.NotFound);
        }
    }

    private async Task<ServiceResult<BypassMergeResultType>> CheckForForcePushAsync(
        string owner, string repo, PullRequest pr)
    {
        try
        {
            var events = await _github.Issue.Timeline.GetAllForIssue(owner, repo, pr.Number);

            var forcePushEvents = events
                .Where(e => e.Event.Value == EventInfoState.HeadRefForcePushed)
                .OrderByDescending(e => e.CreatedAt)
                .ToList();

            if (!forcePushEvents.Any())
            {
                return ServiceResult.Create(BypassMergeResultType.Success);
            }

            var latestForcePush = forcePushEvents.First();

            var masterCommitsAtForcePush = await _github
                .Repository
                .Commit
                .GetAll(
                    owner, repo,
                    new CommitRequest
                    {
                        Sha = pr.Base.Ref,
                        Until = latestForcePush.CreatedAt
                    }
                );

            if (!masterCommitsAtForcePush.Any())
            {
                return ServiceResult.Create(BypassMergeResultType.UnexpectedError,
                    $"Could not determine master state at the time of force push for PR #{pr.Number}.");
            }

            var masterShaAtForcePush = masterCommitsAtForcePush.First().Sha;

            // Merge Base (common commit) between master (at moment of Force Push) and current PR head
            var comparison = await _github.Repository.Commit.Compare(
                owner, repo,
                masterShaAtForcePush,
                pr.Head.Sha);

            // Merge Base should be equal master at the moment of Force Push
            if (comparison.MergeBaseCommit.Sha != masterShaAtForcePush)
            {
                return ServiceResult.Create(BypassMergeResultType.ForcePushDetected,
                    $"PR #{pr.Number} — force push rewrote shared history with {pr.Base.Ref}. " +
                    $"Master was at `{masterShaAtForcePush[..7]}`, " +
                    $"merge base is at `{comparison.MergeBaseCommit.Sha[..7]}`.");
            }

            return ServiceResult.Create(BypassMergeResultType.Success);
        }
        catch (NotFoundException)
        {
            return ServiceResult.Create(BypassMergeResultType.NotFound);
        }
        catch (Exception ex)
        {
            return ServiceResult.Create(BypassMergeResultType.UnexpectedError,
                $"Failed to check force push for PR #{pr.Number}: {ex.Message}");
        }
    }

    private async Task<ServiceResult<BypassMergeResultType>> MergePullRequestAsync(
        string owner, string repo, PullRequest pr)
    {
        try
        {
            await _github.PullRequest.Merge(owner, repo, pr.Number, new MergePullRequest
            {
                CommitMessage = $"[bot] Admin bypass merge of PR #{pr.Number}: {pr.Title}",
                MergeMethod = PullRequestMergeMethod.Merge
            });

            return ServiceResult.Create(BypassMergeResultType.Success);
        }
        catch (PullRequestNotMergeableException)
        {
            return ServiceResult.Create(BypassMergeResultType.NotMergeable);
        }
        catch (Exception ex)
        {
            return ServiceResult.Create(BypassMergeResultType.UnexpectedError,
                $"Unexpected error during merge: {ex.Message}");
        }
    }
}
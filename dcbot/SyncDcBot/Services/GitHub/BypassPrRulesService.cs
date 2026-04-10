using Microsoft.Extensions.Configuration;
using Octokit;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Services.GitHub;

public class BypassPrRulesService
{
    private readonly GitHubClient _github;
    private readonly IConfiguration _config;
    private string Owner => _config["GitHubConfig:RepoOwner"]!;
    private string Repo => _config["GitHubConfig:RepoName"]!;

    public BypassPrRulesService(GitHubClient github, IConfiguration config)
    {
        _github = github;
        _config = config;
    }

    public async Task<ServiceResult<BypassMergeResultType>> BypassMergePullRequestAsync(string prUrl)
    {
        var parseResult = TryParsePullRequestNumber(prUrl, out var prNumber);
        if (!parseResult.IsSuccess) return parseResult;

        var fetchResult = await FetchPullRequestAsync(prNumber);
        if (!fetchResult.IsSuccess) return fetchResult;

        var forcePushResult = await CheckForForcePushAsync(fetchResult.Data!);
        if (!forcePushResult.IsSuccess) return forcePushResult;

        var mergeResult = await MergePullRequestAsync(fetchResult.Data!);
        return mergeResult;
    }

    private ServiceResult<BypassMergeResultType> TryParsePullRequestNumber(string prUrl, out int prNumber)
    {
        prNumber = 0;
        try
        {
            var uri = new Uri(prUrl.Trim());
            var expectedBase = $"github.com/{Owner}/{Repo}/pull/";

            if (!uri.AbsoluteUri.Contains(expectedBase))
            {
                return ServiceResult.Create(BypassMergeResultType.InvalidUrl,
                    $"Invalid PR URL. Expected: `github.com/{Owner}/{Repo}/pull/[number]`");
            }

            var lastSegment = uri.Segments.LastOrDefault()?.Trim('/');
            return ServiceResult.Create(!int.TryParse(lastSegment, out prNumber)
                ? BypassMergeResultType.InvalidPrNumberFormat
                : BypassMergeResultType.Success);
        }
        catch
        {
            return ServiceResult.Create(BypassMergeResultType.InvalidUrl, "Invalid URL format.");
        }
    }

    private async Task<ServiceResult<BypassMergeResultType, PullRequest>> FetchPullRequestAsync(int prNumber)
    {
        try
        {
            var pr = await _github.PullRequest.Get(Owner, Repo, prNumber);

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

            return ServiceResult.CreateWith(BypassMergeResultType
                .Success, pr);
        }
        catch (NotFoundException)
        {
            return ServiceResult.CreateWithDefault<BypassMergeResultType, PullRequest>(BypassMergeResultType
                .NotFound);
        }
    }

    private async Task<ServiceResult<BypassMergeResultType>> CheckForForcePushAsync(PullRequest pr)
    {
        try
        {
            var events = await _github.Issue.Timeline.GetAllForIssue(Owner, Repo, pr.Number);

            var latestForcePush = events
                .Where(e => e.Event.Value == EventInfoState.HeadRefForcePushed)
                .OrderByDescending(e => e.CreatedAt)
                .FirstOrDefault();

            if (latestForcePush is null)
                return ServiceResult.Create(BypassMergeResultType.Success);

            var masterShaAtForcePush = await GetMasterShaAtAsync(pr.Base.Ref, latestForcePush.CreatedAt);
            if (masterShaAtForcePush is null)
            {
                return ServiceResult.Create(BypassMergeResultType.UnexpectedError,
                    $"Could not determine {pr.Base.Ref} state at the time of force push for PR #{pr.Number}.");
            }

            var comparison = await _github.Repository.Commit.Compare(
                Owner, Repo, masterShaAtForcePush, pr.Head.Sha);

            if (comparison.MergeBaseCommit.Sha != masterShaAtForcePush)
            {
                return ServiceResult.Create(BypassMergeResultType.ForcePushDetected,
                    $"PR #{pr.Number} — force push rewrote shared history with {pr.Base.Ref}. " +
                    $"Base was at `{masterShaAtForcePush[..7]}`, " +
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
                $"Failed to check force-push for PR #{pr.Number}: {ex.Message}");
        }
    }

    private async Task<string?> GetMasterShaAtAsync(string branch, DateTimeOffset at)
    {
        var commits = await _github.Repository.Commit.GetAll(
            Owner, Repo,
            new CommitRequest { Sha = branch, Until = at });

        return commits.FirstOrDefault()?.Sha;
    }
    
    private async Task<ServiceResult<BypassMergeResultType>> MergePullRequestAsync(PullRequest pr)
    {
        try
        {
            await _github.PullRequest.Merge(Owner, Repo, pr.Number, new MergePullRequest
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
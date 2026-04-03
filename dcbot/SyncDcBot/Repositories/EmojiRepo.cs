using Discord;

namespace SyncDcBot.Repositories;

public static class EmojiRepo
{
    public static readonly Emoji ErrorEmoji = Emoji.Parse(":x:");
    public static readonly Emoji SuccessEmoji = Emoji.Parse(":white_check_mark:");
}
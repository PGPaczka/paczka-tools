using Discord.Interactions;
using Serilog;

namespace SyncDcBot.Commands;

using ILogger = Serilog.ILogger;

public abstract class CommandBase : InteractionModuleBase<SocketInteractionContext> { }
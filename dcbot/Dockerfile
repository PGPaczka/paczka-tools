FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

COPY SyncDcBot.sln .
COPY SyncDcBot/SyncDcBot.csproj SyncDcBot/
RUN dotnet restore

COPY SyncDcBot/ SyncDcBot/
RUN dotnet publish SyncDcBot/SyncDcBot.csproj \
    -c Release \
    -o /app/publish \
    --no-restore

FROM mcr.microsoft.com/dotnet/runtime:9.0 AS runtime
USER root
WORKDIR /app

COPY --from=build /app/publish .

ENTRYPOINT ["dotnet", "SyncDcBot.dll"]
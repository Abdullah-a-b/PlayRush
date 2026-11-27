"""Retrospective review of directed wins in a bounded observation window."""
from collections import Counter, defaultdict


def network_cases(rows):
    games = Counter()
    total_wins = Counter()
    wins = defaultdict(list)
    concessions = defaultdict(list)
    opponents = defaultdict(set)
    for row in rows:
        a, b = row.low_id, row.high_id
        games[a] += 1
        games[b] += 1
        if row.winner_id not in (a, b):
            continue
        winner = row.winner_id
        loser = b if winner == a else a
        total_wins[winner] += 1
        wins[winner, loser].append(row.match_id)
        opponents[winner].add(loser)
        if row.surrendered:
            concessions[winner, loser].append(row.match_id)

    for winner, rivals in opponents.items():
        # Concentrated concessions to one beneficiary from several accounts.
        donors = sorted(r for r in rivals if len(concessions[winner, r]) >= 2
                       and len(concessions[winner, r]) * 2 >= games[r])
        if len(donors) >= 3:
            yield ("multiple_accounts_conceding_to_one", [winner, *donors],
                   [mid for r in donors for mid in concessions[winner, r]])

        for rival in sorted(rivals):
            matches = wins[winner, rival]
            # A rival consistently loses this matchup despite winning elsewhere.
            other_wins = total_wins[rival] - len(wins.get((rival, winner), ()))
            other_games = games[rival] - len(matches) - len(wins.get((rival, winner), ()))
            if (len(matches) >= 5 and not wins.get((rival, winner)) and other_wins >= 5
                    and other_wins * 4 >= other_games * 3
                    and len(concessions[winner, rival]) >= 2):
                yield ("selective_losses_to_one_opponent", [winner, rival], list(matches))

            # Canonical starting vertex reports each directed triangle once.
            if winner >= rival or len(matches) < 2:
                continue
            for third in opponents.get(rival, set()):
                edges = ((winner, rival), (rival, third), (third, winner))
                if third <= winner or any(len(wins.get(edge, ())) < 2 for edge in edges):
                    continue
                if any(wins.get((b, a)) for a, b in edges):
                    continue
                evidence = [mid for edge in edges for mid in wins[edge]]
                if 2 * len(evidence) >= .8 * sum(games[u] for u in (winner, rival, third)):
                    yield ("concentrated_circular_wins", [winner, rival, third], evidence)

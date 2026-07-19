class haggle:
        SELL=[
            "Seventy percent. It's a clean deal, and the market will bear the rest.",
            "Fair enough. Here's your coin, I'll handle the resale.",
            "Not full value, but it keeps the books balanced. Transaction complete.",
            "You get paid, I get inventory. That's business.",
            "Seventy percent is standard, safe for you, sustainable for me.",
            "I'll take the risk on this one. Your payment's settled.",
            "Efficient trade. Nothing wasted, nothing owed.",
            "This margin keeps the shop running. I'll see it sold.",
            "Coin for card. It's straightforward, and that's the way I like it.",
            "A fair cut, considering the work I'll do moving it forward.",
            "Seventy percent is what I can offer without losing on the resale.",
            "This price reflects the work it takes to move it off my shelves.",
            "I'll take it at seventy percent. Steady business is better than no business.",
            "A fair compromise, you get coin now, I handle the risk later.",
            "That's the margin that keeps the doors open. Here's your share.",
            "Not top value, but quick liquidity always comes at a cost.",
            "Seventy percent is the standing rate. No tricks, just the numbers.",
            "It won't fetch more in the current market. Best to take the offer.",
            "You get guaranteed coin; I take on the uncertainty. Balanced enough.",
            "Consider it sold. Not perfect, but both sides walk away with something."
            ]
        SELL_TERRIBLE =[
            "Hahâ€¦ bold counter. Too bold. If that's your stance, I'll only take it at fifty percent.",
            "Careful now, press too hard, and I reconsider. Fifty percent is all I'll risk.",
            "You should have stopped at my first offer. Now the deal's worse for you.",
            "Interesting. Another collector just walked in with the same card. Value's down.",
            "That counter soured the trade. Half its worth, or I'm not interested.",
            "You make light of my margins, I make light of your card. Fifty percent.",
            "You pushed for more, and in the push I found flaws. This isn't worth full cut.",
            "A bad roll of the dice for you, friend. I can't pay more than half.",
            "Hm. Look closer, corner's bent, gloss is faded. Fifty percent.",
            "The market shifted while we spoke. Oversupply, lower demand. Half its value.",
            "Your offer offended my sense of balance. I'll cut the price down accordingly.",
            "Risk outweighs return. I'll only take it at fifty percent.",
            "That was a poor gamble. You've cost yourself a fairer price.",
            "Ah, just realized I overvalued it. You'll get fifty percent, nothing more.",
            "Another shipment of this card arrived this morning. The value's collapsed.",
            "Pushy talk makes me cautious. Fifty percent is safer for my purse.",
            "Luck wasn't on your side. The card's only worth half in my books now.",
            "I can find better condition copies elsewhere. Half is all I'll offer.",
            "I pride myself on business sense. That sense says fifty percent, no higher.",
            "Your counter tipped the scales the wrong way. This deal sinks to half."
            ]

        SELL_BAD = [
            "You aimed high, but it knocked the price down instead. Sixty percent.",
            "Not a terrible offer, but it makes me cautious. I'll settle at sixty percent.",
            "Hmm. Your counter shaved the margins thin. I'll lower my side to sixty percent.",
            "Negotiation cuts both ways, this time, the cut favors me.",
            "Closer, but not convincing. Sixty percent is as far as I'll go.",
            "I could have met you higher, but your push pulled it down.",
            "Sixty percent. Still coin in your hand, though not what you hoped.",
            "You'll walk away lighter, but I'll call this fair for the risk I take.",
            "Almost had me there. Instead, the deal slides to sixty percent.",
            "Your counter wasn't outrageous, but it does trim the value.",
            "This isn't a loss for you, but it isn't a win either. Sixty percent.",
            "I see where you're coming from, but the market doesn't stretch that far.",
            "A softer miss than some. Sixty percent is a fair compromise.",
            "You pushed, I recalculated. Sixty percent is the number that fits.",
            "Your bargain brought the offer down, but not too severely.",
            "A modest stumble. Still, sixty percent is less painful than it could be.",
            "This leaves me a margin, but only just. Sixty percent.",
            "Not the worst negotiation I've seen, but not the best outcome either.",
            "You nearly had a stronger deal, but the numbers don't lie. Sixty percent.",
            "It could have been worse, fifty percent, even. Sixty percent will keep it steady."
            ]

        SELL_EVEN=[

                "I respect the effort, but seventy percent is as far as this goes.",
                "A reasonable counter, yet the numbers don't budge. Seventy percent.",
                "Good try, but my offer stands. Seventy percent is the rate.",
                "You've got spirit, but I won't sweeten the deal. Seventy percent.",
                "A fair argument, but the market won't support more than seventy percent.",
                "You've made your case, and I've considered it. My price remains.",
                "I admire your push, but the margins won't move. Seventy percent.",
                "Solid attempt, but the shop can't bend further. Seventy percent is final.",
                "Your counter wasn't wasted, I gave it thought. Still, seventy percent.",
                "You didn't lose ground, but you didn't gain any either. Seventy percent.",
                "Negotiation takes skill. You've held even, but not higher.",
                "Seventy percent is firm. It's the number that keeps balance.",
                "A decent bargain, but seventy percent keeps the books honest.",
                "You pressed well, but my rate won't change. Seventy percent.",
                "You've earned my respect, if not a better deal. Seventy percent.",
                "That was closer to convincing, but seventy percent is the ceiling here.",
                "You held your ground, and so did I. Seventy percent.",
                "I weighed your offer against risk. Seventy percent remains the line.",
                "Strong words, steady effort, but the offer stays where it began.",
                "A fair contest of coin and wit. The price is steady at seventy percent."
                ]

        SELL_GOOD=[
                "You've made a strong case. I'll stretch to eighty percent.",
                "Not my usual rate, but your effort warrants it. Eighty percent.",
                "You pressed well. I'll concede a little, eighty percent.",
                "I'll allow it. Eighty percent, but don't expect that often.",
                "Your counter has weight. I'll raise my offer accordingly.",
                "A fair challenge deserves a fairer price. Eighty percent.",
                "You've earned more than the standard cut. Eighty percent it is.",
                "My margins shrink, but I'll honor your haggling skill.",
                "You argued wisely. Eighty percent is the best I can do.",
                "I'll not ignore a good negotiator. Here's eighty percent.",
                "A step higher, but only because you've shown me reason.",
                "The Sleeve doesn't yield easily, but eighty percent feels just.",
                "I rarely budge, but this time I'll shift. Eighty percent.",
                "Not bad. You pulled me higher than I planned.",
                "Eight of ten coins back. That's generosity by shop standards.",
                "You found some room in the margins. Eighty percent.",
                "Not my preferred deal, but you've earned the adjustment.",
                "A stronger hand than most. Eighty percent is yours.",
                "You walk away with more than the standard. Be satisfied.",
                "You negotiated well. I'll give ground, but no more than eighty percent."
                ]

        SELL_GREAT=[
                "Well struck. You'll have ninety percent, few manage that here.",
                "Impressive. I'll part with more coin than I planned.",
                "You've bested me at the table. Ninety percent it is.",
                "Not many can turn my rate upward. Consider this a rare success.",
                "Your words carry weight. Ninety percent is deserved.",
                "I admire that push. Here's ninety, don't expect it twice.",
                "Well-argued. I'll bend further than most would think.",
                "You found the edge of my ledger. Ninety percent.",
                "A rare hand to play so well. You've earned near full value.",
                "That was a masterful counter. The Sleeve yields, this once.",
                "Ninety percentâ€¦ consider it both profit and compliment.",
                "Sharp tongue, steady wit. You've forced my hand.",
                "I give you ninety percent. Not common, not easy, but earned.",
                "Well bargained. The margin's slim, yet fair.",
                "I see no shame in conceding here. Ninety percent.",
                "Few walk out with this much. Call it skill, call it luck.",
                "Your haggling leaves me lighter than most. Ninety percent it is.",
                "I'll not deny talent. You've driven me higher than usual.",
                "I deal in coin and reason. You've proven both. Ninety percent.",
                "Business favors the bold, today, you leave with ninety percent."
                ]


        BUY=[
                "Fifty percent markup is the rate. Fair trade for both sides.",
                "That's the standing price, fifty percent markup keeps the books balanced.",
                "You pay the premium, I provide the card. Simple.",
                "Standard markup, nothing more.",
                "Coin at fifty percent markup secures the card today.",
                "That covers the overhead and risk. Fifty percent markup it is.",
                "Pay the rate, take the card. Efficient business.",
                "Fifty percent markup, keeps the Sleeve open and the cards flowing.",
                "You know the value, I know the margin. Fifty percent markup stands.",
                "The card moves, the coin lands. Fifty percent markup.",
                "I'll part with it at the standard premium. Fifty percent markup.",
                "A fair exchange, higher than face, lower than scarcity would demand.",
                "This is the usual markup. Nothing hidden, nothing added.",
                "Coin for card at the set rate: fifty percent markup.",
                "The shop runs on margins like these. Fifty percent markup keeps us even.",
                "Not a bargain, not a loss. Fifty percent markup is the middle ground.",
                "That's the market rate. Straightforward and steady.",
                "A premium price, but a guaranteed trade.",
                "At a fifty percent markup, the Sleeve's shelves stay full, and yours do too.",
                "I won't haggle on it. This card leaves at a fifty percent markup."
                ]

        BUY_TERRIBLE=[

                "Careful, push too hard and I'll raise the price. Seventy percent markup.",
                "That counter made me rethink the rarity. Price goes up.",
                "You pressed poorly. Seventy percent markup, or no card at all.",
                "Offended the ledger, have you? That'll cost you.",
                "Bold talk, but it only makes the deal steeper.",
                "You misplayed your hand. Seventy percent markup's the new rate.",
                "I see now, this card's worth more than I thought. Price adjusted.",
                "Try to cut too deep, and the blade turns back on you.",
                "Seventy percent markup. The market shifted while you argued.",
                "Poorly handled. My margin just grew, not yours.",
                "I don't tolerate reckless bargaining. The price rises.",
                "A hasty counter, a harsher cost. Seventy percent markup.",
                "Pressing too far soured the deal. The value climbs.",
                "Interesting approach. Pity it costs you coin instead.",
                "I've reconsidered its place on my shelf, rarity demands more.",
                "Push too much, and the Sleeve pushes back.",
                "I adjusted my books mid-talk. Seventy percent markup now.",
                "That was a gamble, and the dice betrayed you.",
                "Overplayed your hand. Seventy percent markup.",
                "You wanted a bargain; you earned the opposite."
                ]

        BUY_BAD=[
                "Your push didn't land. Price climbs to a sixty percent markup.",
                "Closer than most, but the math tilts against you.",
                "That counter trims my patience, not the price.",
                "Reasonable attempt, but I won't lose margin. Sixty percent markup.",
                "The Sleeve doesn't bend easily. Price rises to a sixty percent markup.",
                "A slight misstep in haggling, this card will now cost more.",
                "You wanted less, but your words had the opposite effect.",
                "Push too far, and the numbers push back.",
                "Not disastrous, but you'll pay a premium now.",
                "Your offer was heard. My price is higher.",
                "Not the worst bargain struck, though you've raised the stakes.",
                "You tried to cut the deal thin. Instead, it thickened.",
                "The margins move the wrong way for you. Sixty percent markup.",
                "A stumble, but not a fall. The cost sits at a sixty percent markup.",
                "The card's in demand, I won't let it go for less. In fact, more.",
                "You pressed harder than the value allowed.",
                "Respectable try, poor result. Price adjusted upward.",
                "Market's tight. A weaker haggle only makes it steeper.",
                "This deal favors me now. Sixty percent markup.",
                "Your hand wavered in the game of coin. Price goes up."
                ]

        BUY_EVEN=[
                "A fair attempt, but the price holds at a fifty percent markup.",
                "Good effort, but the ledger doesn't budge. Fifty percent markup.",
                "Respectable words, steady offer, but the rate stands firm.",
                "I weighed it carefully. Fifty percent markup remains.",
                "You didn't cost yourself, but you didn't gain either.",
                "A solid try, but this card sells at a fifty percent markup. Always.",
                "I admire your haggling, but my price doesn't shift.",
                "No ground lost, no ground gained. Fifty percent markup.",
                "Strong push, but I won't sweeten the deal. Price stays.",
                "This is the shop's rate. Fifty percent markup, no more, no less.",
                "Not poor, not brilliant. A steady deal at a fifty percent markup.",
                "You held your ground, and so did I.",
                "I considered it, but a fifty percent markup is balanced.",
                "My price holds firm, regardless of the attempt.",
                "Negotiation ends where it began. Fifty percent markup.",
                "Not a loss, not a win. The rate remains unchanged.",
                "You've proven your spirit, but the cost is set.",
                "A good contest, but the market doesn't move.",
                "That's as fair as this trade gets, fifty percent markup.",
                "You tried well, but I deal in constants. Fifty percent markup."
                ]

        BUY_GOOD=[
                "Well-argued. I'll bring it down to a forty percent markup.",
                "You've earned a slimmer margin from me. Forty percent markup it is.",
                "Not easy to bend my rate, but you've managed it.",
                "I'll concede a little ground. Price rests at a forty percent markup.",
                "Respectable negotiation. You'll pay less than most.",
                "Not full victory, but you've trimmed the cost.",
                "Forty percent markup. Still profit for me, but not as much.",
                "Your words found room in the margins. Well done.",
                "You chipped away at the price. I'll honor it.",
                "You've earned a concession. The new rate is a forty percent markup.",
                "I won't deny the effort. A fairer price this time.",
                "Good bargaining. You'll save a coin or two.",
                "I'll allow it. Forty percent markup, but don't expect more.",
                "Your push didn't go unheard. I'll meet you partway.",
                "Forty percent markup, less than my usual, but deserved.",
                "A strong case. I'll cut the cost accordingly.",
                "Not the deal I'd prefer, but the market can bend.",
                "Your persistence has weight. I'll lower the figure.",
                "This time, the Sleeve gives a little.",
                "A fair trade, even if it narrows my margin."
                ]

        BUY_GREAT=[
                "Well done. Few drive me this low. Thirty percent markup it is.",
                "You argued with precision. The price falls to a thirty percent markup.",
                "That was masterful. I'll let it go for less than most ever see.",
                "Impressive. You've carved the price nearly to the bone.",
                "I don't often yield this far. Thirty percent markup.",
                "A rare concession. You've earned it.",
                "Skill and reason win the day. The card is yours for a thirty percent markup.",
                "Consider it a victory. Few walk away with this bargain.",
                "Your case was airtight. I can't deny it.",
                "This margin leaves me thin, but the haggle was fair.",
                "You pressed perfectly. I'll give ground this once.",
                "Well bargained. You won't see many deals like this again.",
                "Your words struck true. The Sleeve lowers its price.",
                "Rarely do I concede so much. Today, you've earned it.",
                "My respect, and your discount. Thirty percent markup.",
                "You leave with both the card and the upper hand.",
                "Not often am I bested. You've done well.",
                "Your wit outweighed my caution. Thirty percent markup it is.",
                "This deal favors you more than most. Remember it.",
                "Business respects talent. You've proven yours."
                ]

class desc:
    LOTTO='''"Getch'yer Satchemon Lottery Tickets here! The current JACKPOT is {} GP!"
    The Satchemon Lottery is a way for you to WIN BIG!

    Every Sunday night at 9:00 P.M. EST, a random number will be generated between 0000 and 9999. Individuals that have bought tickets for the lottery could potentially win cold hard GP for matching all or part of the generated number. Below is a layout of the prize structure:

    Match 1 digit: 5 GP (Odds - 1 in 3.43) 
    Match 2 digits: 80 GP (Odds - 1 in 21)
    Match 3 digits: 2,000 GP (Odds - 1 in 278)
    Match all 4 digits: JACKPOT Starts at 40,000 GP (Odds - 1 in 10,000)

    Every week that passes without a jackpot winner, 10% of ticket sales for that week will be added to the jackpot. After a jackpot is won, it will be reset to 40,000 GP.

    If multiple individuals match all 4 numbers in the same drawing, the jackpot will be split evenly among the winners.

    Winning numbers and matching tickets will be announced in the Satchemon Chat channel

    Tickets cost 25 GP each.

    To buy tickets, use the same /LOTTO command you entered, then select the "howmanycards" option to specify a number of tickets you would like to purchase.

    Good Luck!'''
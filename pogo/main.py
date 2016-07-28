#!/usr/bin/python
"""


"""
import argparse
import logging
import time
import sys
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

from pokedex import pokedex
from inventory import items
import numpy as np

start_time = time.time()
#==============================================================================

ROUND = 300000 # (pokemon get + poke stop) * ROUND

IS_RESET_LOCATION = True # If True, reset location using initial location
RESET_LOCATION_ROUND = 30

STEP = 9 # 32.52km/h

IS_TELEPORT = False # If True, when reached RESET_LOCATION_ROUND, go to TELEPORT_SPOTS
                    # If False, go to initial location

#TELEPORT_SPOTS = ["35.698828091221095, 139.81614768505096",  #kinsi park
#                  "35.6847861149, 139.71041500",             #gyoen
#                  "35.64387036252, 139.68159198760",         #setagaya park
#                  "35.673787818, 139.75635051",              #hibiya park
#                  "35.671687337020, 139.6953570842",         #yoyogi park
#                  ]

TELEPORT_SPOTS = ["35.6717352739260, 139.764568805694",  #ginza
                  "35.692158133974, 139.7709846496",     #kanda
                  "35.66697194, 139.749805",             #toranomon
                  ]


#==============================================================================
# raw input
#==============================================================================

raw = raw_input('POKESTOP MARATHON mode??(y/n) >>>')
if raw == 'y':
    POKESTOP_MARATHON = True # If True, not to try to catch Pokemon
    MODE = 'POKESTOP MARATHON mode'
elif raw == 'n':
    POKESTOP_MARATHON = False
    MODE = 'Catch and Pokestop mode'
else:
    raise Exception('input y/n')

raw = raw_input('RANDOM ACCESS to Pokestop??(y/n) >>>')
if raw == 'y':
    RANDOM_ACCESS = True # If True, not to try to catch Pokemon
    MODE += '(Random access)'
elif raw == 'n':
    RANDOM_ACCESS = False
    MODE += '(Closest access)'
else:
    raise Exception('input y/n')


#raw = raw_input('STEP??(if 3.2, move at 11.52km/h) >>>')
#if raw.isdigit():
#    STEP = float(raw)
#else:
#    raise Exception('input float')




#==============================================================================
# def
#==============================================================================
def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('Line %(lineno)d,%(filename)s - %(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# Example functions
# Get profile
def getProfile(session):
        logging.info("Printing Profile:")
        profile = session.getProfile()
        logging.info(profile)


# Grab the nearest pokemon details
def findBestPokemon(session):
    # Get Map details and print pokemon
    logging.info("Finding Nearby Pokemon:")
    cells = session.getMapObjects()
    closest = float("Inf")
    best = -1
    pokemonBest = None
    latitude, longitude, _ = session.getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    for cell in cells.map_cells:
        # Heap in pokemon protos where we have long + lat
        pokemons = [p for p in cell.wild_pokemons] + [p for p in cell.catchable_pokemons]
        for pokemon in pokemons:
            # Normalize the ID from different protos
            pokemonId = getattr(pokemon, "pokemon_id", None)
            if not pokemonId:
                pokemonId = pokemon.pokemon_data.pokemon_id

            # Find distance to pokemon
            dist = Location.getDistance(
                latitude,
                longitude,
                pokemon.latitude,
                pokemon.longitude
            )

            # Log the pokemon found
            logging.info("%s, %f meters away" % (
                pokedex[pokemonId],
                dist
            ))

            rarity = pokedex.getRarityById(pokemonId)
            # Greedy for rarest
            if rarity > best:
                pokemonBest = pokemon
                best = rarity
                closest = dist
            # Greedy for closest of same rarity
            elif rarity == best and dist < closest:
                pokemonBest = pokemon
                closest = dist
    return pokemonBest


# Wrap both for ease
def encounterAndCatch(session, pokemon, thresholdP=0.5, limit=5, delay=2):
    # Start encounter
    session.encounterPokemon(pokemon)
    
    # Have we used a razz berry yet?
    berried = False

    # Make sure we aren't over limit
    count = 0

    # Attempt catch
    while True:
        #initialize inventory
        bag = session.checkInventory().bag
        
        # try a berry
        if not berried and items.RAZZ_BERRY in bag and bag[items.RAZZ_BERRY]:
            logging.info("Using a RAZZ_BERRY")
            session.useItemCapture(items.RAZZ_BERRY, pokemon)
            berried = True
            time.sleep(delay)
            continue
        
        # Get ball list
        balls = [items.POKE_BALL] * bag[items.POKE_BALL] + \
                [items.GREAT_BALL] * bag[items.GREAT_BALL] + \
                [items.ULTRA_BALL] * bag[items.ULTRA_BALL]

        # Choose ball with randomness
        # if no balls, there are no balls in bag
        if len(balls) == 0:
            print "Out of usable balls"
            break
        else:
            bestBall = np.random.choice(balls)

        # Try to catch it!!
        logging.info("Using a %s" % items[bestBall])
        attempt = session.catchPokemon(pokemon, bestBall)
        time.sleep(delay)

        # Success or run away
        if attempt.status == 1:
            return attempt

        # CATCH_FLEE is bad news
        if attempt.status == 3:
            logging.info("Possible soft ban.")
            return attempt

        # Only try up to x attempts
        count += 1
        if count >= limit:
            logging.info("Over catch limit")
            return None


# Catch a pokemon at a given point
def walkAndCatch(session, pokemon):
    if pokemon:
        logging.info("Catching %s:" % pokedex[pokemon.pokemon_data.pokemon_id])
        session.walkTo(pokemon.latitude, pokemon.longitude, step=STEP*np.random.uniform(0.95,1.05))
        logging.info(encounterAndCatch(session, pokemon))


# Do Inventory stuff
def getInventory(session):
    logging.info("Get Inventory:")
    logging.info(session.getInventory())


# Basic solution to spinning all forts.
# Since traveling salesman problem, not
# true solution. But at least you get
# those step in
def sortCloseForts(session):
    # Sort nearest forts (pokestop)
    logging.info("Sorting Nearest Forts:")
    cells = session.getMapObjects()
    latitude, longitude, _ = session.getCoordinates()
    ordered_forts = []
    for cell in cells.map_cells:
        for fort in cell.forts:
            dist = Location.getDistance(
                latitude,
                longitude,
                fort.latitude,
                fort.longitude
            )
            if fort.type == 1 and fort.cooldown_complete_timestamp_ms<time.time():
                ordered_forts.append({'distance': dist, 'fort': fort})

    ordered_forts = sorted(ordered_forts, key=lambda k: k['distance'])
    return [instance['fort'] for instance in ordered_forts]


# Find the fort closest to user
def findClosestFort(session):
    # Find nearest fort (pokestop)
    logging.info("Finding Nearest Fort:")
    if RANDOM_ACCESS:
        return sortCloseForts(session)[np.random.randint(1,5)]
    return sortCloseForts(session)[0]



# Walk to fort and spin
def walkAndSpin(session, fort):
    # No fort, demo == over
    if fort:
        details = session.getFortDetails(fort)
        logging.info("Spinning the Fort \"%s\":" % details.name)

        # Walk over
        session.walkTo(fort.latitude, fort.longitude, step=STEP*np.random.uniform(0.95,1.05))
        # Give it a spin
        fortResponse = session.getFortSearch(fort)
        logging.info(fortResponse)


# Walk and spin everywhere
def walkAndSpinMany(session, forts):
    for fort in forts:
        walkAndSpin(session, fort)


# A very brute force approach to evolving
def evolveAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        logging.info(session.evolvePokemon(pokemon))
        time.sleep(1)


# You probably don't want to run this
def releaseAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        session.releasePokemon(pokemon)
        time.sleep(1)


# Just incase you didn't want any revives
def tossRevives(session):
    bag = session.checkInventory().bag
    return session.recycleItem(items.REVIVE, bag[items.REVIVE])


# Set an egg to an incubator
def setEgg(session):
    inventory = session.checkInventory()

    # If no eggs, nothing we can do
    if len(inventory.eggs) == 0:
        return None

    egg = inventory.eggs[0]
    incubator = inventory.incubators[0]
    return session.setEgg(incubator, egg)

def evolvePokemon(session):
    party = session.checkInventory().party
    # You may edit this list
    evolables = [pokedex.PIDGEY, pokedex.RATTATA, pokedex.ZUBAT, 
                 pokedex.CATERPIE, pokedex.WEEDLE, 
                 pokedex.DODUO]
    
    for evolve in evolables:
        pokemons = [pokemon for pokemon in party if evolve == pokemon.pokemon_id]
        candies_current = session.checkInventory().candies[evolve]
        candies_needed = pokedex.evolves[evolve]
        
        i = 0
        while i != len(pokemons) and candies_needed < candies_current:
            pokemon = pokemons[i]
            logging.info("Evolving %s" % pokedex[pokemon.pokemon_id])
            logging.info(session.evolvePokemon(pokemon))
            time.sleep(1)
            session.releasePokemon(pokemon)
            time.sleep(1)
            candies_current -= candies_needed
            i +=1
    
def releasePokemon(session, threasholdCP=500):
    party = session.checkInventory().party
    
    for pokemon in party:
        # If low cp, throw away
        if pokemon.cp < threasholdCP:
            # Get rid of low CP, low evolve value
            logging.info("Releasing %s" % pokedex[pokemon.pokemon_id])
            session.releasePokemon(pokemon)
            
# Understand this function before you run it.
# Otherwise you may flush pokemon you wanted.
def cleanPokemon(session):
    logging.info("Cleaning out Pokemon...")
    evolvePokemon(session)
    releasePokemon(session, threasholdCP=500)

def cleanInventory(session):
    logging.info("Cleaning out Inventory...")
    bag = session.checkInventory().bag

    # Clear out all of a crtain type
    tossable = [items.POTION, items.SUPER_POTION, items.REVIVE]
    for toss in tossable:
        if toss in bag and bag[toss]:
            session.recycleItem(toss, bag[toss])

    # Limit a certain type
    limited = {
        items.POKE_BALL: 50,
        items.GREAT_BALL: 100,
        items.ULTRA_BALL: 150,
        items.RAZZ_BERRY: 25
    }
    for limit in limited:
        if limit in bag and bag[limit] > limited[limit]:
            session.recycleItem(limit, bag[limit] - limited[limit])


# Basic bot
def simpleBot(session):
    # Trying not to flood the servers
    cooldown = 1

    # Run the bot
    while True:
        forts = sortCloseForts(session)
        cleanPokemon(session, thresholdCP=300)
        cleanInventory(session)
        try:
            for fort in forts:
                pokemon = findBestPokemon(session)
                walkAndCatch(session, pokemon)
                walkAndSpin(session, fort)
                cooldown = 1
                time.sleep(1)

        # Catch problems and reauthenticate
        except GeneralPogoException as e:
            logging.critical('GeneralPogoException raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)
            cooldown *= 2

        except Exception as e:
            logging.critical('Exception raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)
            cooldown *= 2


# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    setupLogger()
    logging.debug('Logger set up')

    print 'Read in args'
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auth", help="Auth Service", required=True)
    parser.add_argument("-u", "--username", help="Username", required=True)
    parser.add_argument("-p", "--password", help="Password", required=True)
    parser.add_argument("-l", "--location", help="Location", required=True)
    parser.add_argument("-g", "--geo_key", help="GEO API Secret")
    args = parser.parse_args()

    print 'Check service'
    if args.auth not in ['ptc', 'google']:
        logging.error('Invalid auth service {}'.format(args.auth))
        sys.exit(-1)

    print 'Create PokoAuthObject'
    poko_session = PokeAuthSession(
        args.username,
        args.password,
        args.auth,
        geo_key=args.geo_key
    )

    print 'Authenticate with a given location'
    # Location is not inherent in authentication
    # But is important to session
    if POKESTOP_MARATHON:
        raw = raw_input('START from Ginza??(y/n) >>>')
        if raw == 'y':
            raw = True # If True, not to try to catch Pokemon
        elif raw == 'n':
            raw = False
        else:
            raise Exception('input y/n')
    if POKESTOP_MARATHON and raw:
        args.location = "35.6717352739260, 139.764568805694"
    session = poko_session.authenticate(args.location)

    # Time to show off what we can do
    if session:

        # General
        getProfile(session)
        getInventory(session)
        cleanInventory(session)
        setEgg(session)

        for i in range(ROUND):
            print '-='*40
            print 'ROUND:',i+1,'(/',ROUND,')'
            print 'MODE:',MODE
            print 'elapsed time:',round((time.time()-start_time)/60,5),'min'
            
            print '-='*40
            
            # Reset location related
            if IS_RESET_LOCATION and i>0 and i%RESET_LOCATION_ROUND==0:
                if IS_TELEPORT:
                    args.location = np.random.choice(TELEPORT_SPOTS)
                print 'RESET LOCATION:',args.location
                lat, lon = map(float,args.location.split(','))
                session.walkTo(lat, lon, step=STEP*np.random.uniform(0.95,1.05))
            
            # Pokemon related
            if not POKESTOP_MARATHON:
                #cleanPokemon(session) # BE SURE TO COMFIRM IF IT'S OK TO RUN THIS!
                pokemon = findBestPokemon(session)
                walkAndCatch(session, pokemon)
    
            # Pokestop related
            fort = findClosestFort(session)
            walkAndSpin(session, fort)
            
            if i%50==0:
                cleanInventory(session)
                setEgg(session)

        # see simpleBot() for logical usecases
        # eg. simpleBot(session)

    else:
        logging.critical('Session not created successfully')

========
Examples
========

-------------------------
Creating a simple machine
-------------------------

.. testcode::

    from automaton import machines
    m = machines.FiniteMachine()
    m.add_state('up')
    m.add_state('down')
    m.add_transition('down', 'up', 'jump')
    m.add_transition('up', 'down', 'fall')
    m.default_start_state = 'down'
    print(m.pformat())

**Expected output:**

.. testoutput::

    +---------+-------+------+----------+---------+
    |  Start  | Event | End  | On Enter | On Exit |
    +---------+-------+------+----------+---------+
    | down[^] |  jump |  up  |    .     |    .    |
    |    up   |  fall | down |    .     |    .    |
    +---------+-------+------+----------+---------+

------------------------------
Transitioning a simple machine
------------------------------

.. testcode::

    m.initialize()
    m.process_event('jump')
    print(m.pformat())
    print(m.current_state)
    print(m.terminated)
    m.process_event('fall')
    print(m.pformat())
    print(m.current_state)

**Expected output:**

.. testoutput::

    +---------+-------+------+----------+---------+
    |  Start  | Event | End  | On Enter | On Exit |
    +---------+-------+------+----------+---------+
    | down[^] |  jump |  up  |    .     |    .    |
    |   @up   |  fall | down |    .     |    .    |
    +---------+-------+------+----------+---------+
    up
    False
    +----------+-------+------+----------+---------+
    |  Start   | Event | End  | On Enter | On Exit |
    +----------+-------+------+----------+---------+
    | @down[^] |  jump |  up  |    .     |    .    |
    |    up    |  fall | down |    .     |    .    |
    +----------+-------+------+----------+---------+
    down
    False


-------------------------
Running a complex machine
-------------------------

.. testcode::

    from automaton import machines
    from automaton import runners


    # These reaction functions will get triggered when the registered state
    # and event occur, it is expected to provide a new event that reacts to the
    # new stable state (so that the state-machine can transition to a new
    # stable state, and repeat, until the machine ends up in a terminal
    # state, whereby it will stop...)

    def react_to_squirrel(old_state, new_state, event_that_triggered):
        return "gets petted"


    def react_to_wagging(old_state, new_state, event_that_triggered):
        return "gets petted"


    m = machines.FiniteMachine()

    m.add_state("sits")
    m.add_state("lies down", terminal=True)
    m.add_state("barks")
    m.add_state("wags tail")

    m.default_start_state = 'sits'

    m.add_transition("sits", "barks", "squirrel!")
    m.add_transition("barks", "wags tail", "gets petted")
    m.add_transition("wags tail", "lies down", "gets petted")

    m.add_reaction("barks", "squirrel!", react_to_squirrel)
    m.add_reaction('wags tail', "gets petted", react_to_wagging)

    print(m.pformat())
    r = runners.FiniteRunner(m)
    for (old_state, new_state) in r.run_iter("squirrel!"):
        print("Leaving '%s'" % old_state)
        print("Entered '%s'" % new_state)

**Expected output:**

.. testoutput::

    +--------------+-------------+-----------+----------+---------+
    |    Start     |    Event    |    End    | On Enter | On Exit |
    +--------------+-------------+-----------+----------+---------+
    |    barks     | gets petted | wags tail |    .     |    .    |
    | lies down[$] |      .      |     .     |    .     |    .    |
    |   sits[^]    |  squirrel!  |   barks   |    .     |    .    |
    |  wags tail   | gets petted | lies down |    .     |    .    |
    +--------------+-------------+-----------+----------+---------+
    Leaving 'sits'
    Entered 'barks'
    Leaving 'barks'
    Entered 'wags tail'
    Leaving 'wags tail'
    Entered 'lies down'

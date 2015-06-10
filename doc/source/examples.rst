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


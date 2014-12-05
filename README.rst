=========
Automaton
=========

.. image:: https://travis-ci.org/harlowja/automaton.png?branch=master
   :target: https://travis-ci.org/harlowja/automaton

Friendly state machines for python.

Examples
~~~~~~~~

**Squirrel**::

    >>> from automaton import machines
    >>> f = machines.FiniteMachine("sits")
    >>> f.add_state("sits")
    >>> f.add_state("barks")
    >>> f.add_state("wags tail")
    >>> f.add_transition("sits", "barks", "squirrel!")
    >>> f.add_transition("barks", "wags tail", "gets petted")
    >>> f.add_transition("wags tail", "sits", "gets petted")
    >>> f.add_transition("wags tail", "barks", "squirrel!")
    >>> print(f.pformat())
    +-----------+-------------+-----------+----------+---------+
    |   Start   |    Event    |    End    | On Enter | On Exit |
    +-----------+-------------+-----------+----------+---------+
    |   barks   | gets petted | wags tail |    .     |    .    |
    |  sits[^]  |  squirrel!  |   barks   |    .     |    .    |
    | wags tail | gets petted |    sits   |    .     |    .    |
    | wags tail |  squirrel!  |   barks   |    .     |    .    |
    +-----------+-------------+-----------+----------+---------+

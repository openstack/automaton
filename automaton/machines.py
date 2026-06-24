#    Copyright (C) 2014 Yahoo! Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
from collections.abc import Callable, Generator, Mapping, Sequence
from typing import Any, Protocol, NotRequired, Self, TypedDict

import prettytable

from automaton import _utils as utils
from automaton import exceptions as excp

OnEnterCallbackT = Callable[[str, str], None] | None
OnExitCallbackT = Callable[[str, str], None] | None


class State:
    """Container that defines needed components of a single state.

    Usage of this and the :meth:`~.FiniteMachine.build` make creating finite
    state machines that much easier.

    :ivar name: The name of the state.
    :ivar is_terminal: Whether this state is terminal (or not).
    :ivar next_states: Dictionary of 'event' -> 'next state name' (or none).
    :ivar on_enter: callback that will be called when the state is entered.
    :ivar on_exit: callback that will be called when the state is exited.
    """

    def __init__(
        self,
        name: str,
        is_terminal: bool = False,
        next_states: Mapping[str, str] | None = None,
        on_enter: OnEnterCallbackT | None = None,
        on_exit: OnExitCallbackT | None = None,
    ) -> None:
        self.name = name
        self.is_terminal = bool(is_terminal)
        self.next_states = next_states
        self.on_enter = on_enter
        self.on_exit = on_exit


class StateDict(TypedDict, total=False):
    name: str
    is_terminal: bool
    next_states: dict[str, str] | None
    on_enter: OnEnterCallbackT | None
    on_exit: OnExitCallbackT | None


def _convert_to_states(
    state_space: Sequence[State | StateDict],
) -> Generator[State, None, None]:
    # NOTE(harlowja): if provided dicts, convert them...
    for state in state_space:
        if isinstance(state, dict):
            yield State(**state)
        else:
            yield state


def _orderedkeys(data: Mapping[str, Any], sort: bool = True) -> list[str]:
    if sort:
        return sorted(data)
    else:
        return list(data)


class _Jump:
    """A FSM transition tracks this data while jumping."""

    def __init__(
        self, name: str, on_enter: OnEnterCallbackT, on_exit: OnExitCallbackT
    ) -> None:
        self.name = name
        self.on_enter = on_enter
        self.on_exit = on_exit


# We can't use ellipsis with concatenate until Python 3.11 so this our
# workaround
#
# https://github.com/python/cpython/pull/30969
class ReactionProtocol(Protocol):
    def __call__(
        self,
        old_state: str | None,
        new_state: str | None,
        event: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...


class _TrackedState(TypedDict):
    terminal: bool
    reactions: dict[
        str, tuple[ReactionProtocol, tuple[Any, ...], dict[str, Any]]
    ]
    on_enter: OnEnterCallbackT
    on_exit: OnExitCallbackT
    machine: NotRequired['FiniteMachine']


class FiniteMachine:
    """A finite state machine.

    This state machine can be used to automatically run a given set of
    transitions and states in response to events (either from callbacks or from
    generator/iterator send() values, see PEP 342). On each triggered event, a
    ``on_enter`` and ``on_exit`` callback can also be provided which will be
    called to perform some type of action on leaving a prior state and before
    entering a new state.

    NOTE(harlowja): reactions will *only* be called when the generator/iterator
    from :py:meth:`~automaton.runners.Runner.run_iter` does *not* send
    back a new event (they will always be called if the
    :py:meth:`~automaton.runners.Runner.run` method is used). This allows
    for two unique ways (these ways can also be intermixed) to use this state
    machine when using :py:meth:`~automaton.runners.Runner.run`; one
    where *external* event trigger the next state transition and one
    where *internal* reaction callbacks trigger the next state
    transition. The other way to use this
    state machine is to skip using  :py:meth:`~automaton.runners.Runner.run`
    or :py:meth:`~automaton.runners.Runner.run_iter`
    completely and use the :meth:`~.FiniteMachine.process_event` method
    explicitly and trigger the events via
    some *external* functionality/triggers...
    """

    #: The result of processing an event (cause and effect...)
    Effect = collections.namedtuple('Effect', 'reaction,terminal')

    @classmethod
    def _effect_builder(
        cls, new_state: Mapping[str, Any], event: str
    ) -> Effect:
        return cls.Effect(
            new_state['reactions'].get(event), new_state["terminal"]
        )

    def __init__(self) -> None:
        self._transitions: dict[str, dict[str, _Jump]] = {}
        self._states: dict[str, _TrackedState] = {}
        self._default_start_state: str | None = None
        self._current: _Jump | None = None
        self.frozen = False

    @property
    def default_start_state(self) -> str | None:
        """Sets the *default* start state that the machine should use.

        NOTE(harlowja): this will be used by ``initialize`` but only if that
        function is not given its own ``start_state`` that overrides this
        default.
        """
        return self._default_start_state

    @default_start_state.setter
    def default_start_state(self, state: str) -> None:
        if self.frozen:
            raise excp.FrozenMachine()

        if state not in self._states:
            raise excp.NotFound(
                f"Can not set the default start state to undefined state "
                f"'{state}'"
            )

        self._default_start_state = state

    @classmethod
    def build(
        cls, state_space: Sequence[State | StateDict]
    ) -> 'FiniteMachine':
        """Builds a machine from a state space listing.

        Each element of this list must be an instance
        of :py:class:`.State` or a ``dict`` with equivalent keys that
        can be used to construct a :py:class:`.State` instance.
        """
        normalized_states = list(_convert_to_states(state_space))
        m = cls()
        for state in normalized_states:
            m.add_state(
                state.name,
                terminal=state.is_terminal,
                on_enter=state.on_enter,
                on_exit=state.on_exit,
            )
        for state in normalized_states:
            if state.next_states:
                for event, next_state in state.next_states.items():
                    if isinstance(next_state, State):
                        next_state = next_state.name
                    m.add_transition(state.name, next_state, event)
        return m

    @property
    def current_state(self) -> str | None:
        """The current state the machine is in (or none if not initialized)."""
        if self._current is not None:
            return self._current.name
        return None

    @property
    def terminated(self) -> bool:
        """Returns whether the state machine is in a terminal state."""
        if self._current is None:
            return False
        return bool(self._states[self._current.name]['terminal'])

    def add_state(
        self,
        state: str,
        terminal: bool = False,
        on_enter: OnEnterCallbackT = None,
        on_exit: OnExitCallbackT = None,
    ) -> None:
        """Adds a given state to the state machine.

        The ``on_enter`` and ``on_exit`` callbacks, if provided will be
        expected to take two positional parameters, these being the state
        being exited (for ``on_exit``) or the state being entered (for
        ``on_enter``) and a second parameter which is the event that is
        being processed that caused the state transition.
        """
        if self.frozen:
            raise excp.FrozenMachine()
        if state in self._states:
            raise excp.Duplicate(f"State '{state}' already defined")
        if on_enter is not None:
            if not callable(on_enter):
                raise ValueError("On enter callback must be callable")
        if on_exit is not None:
            if not callable(on_exit):
                raise ValueError("On exit callback must be callable")
        self._states[state] = {
            'terminal': bool(terminal),
            'reactions': {},
            'on_enter': on_enter,
            'on_exit': on_exit,
        }
        self._transitions[state] = {}

    def is_actionable_event(self, event: str) -> bool:
        """Check whether the event is actionable in the current state."""
        current = self._current
        if current is None:
            return False
        if event not in self._transitions[current.name]:
            return False
        return True

    def add_reaction(
        self,
        state: str,
        event: str,
        reaction: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Adds a reaction that may get triggered by the given event & state.

        Reaction callbacks may (depending on how the state machine is ran) be
        used after an event is processed (and a transition occurs) to cause the
        machine to react to the newly arrived at stable state.

        These callbacks are expected to accept three default positional
        parameters (although more can be passed in via *args and **kwargs,
        these will automatically get provided to the callback when it is
        activated *ontop* of the three default). The three default parameters
        are the last stable state, the new stable state and the event that
        caused the transition to this new stable state to be arrived at.

        The expected result of a callback is expected to be a new event that
        the callback wants the state machine to react to. This new event
        may (depending on how the state machine is ran) get processed (and
        this process typically repeats) until the state machine reaches a
        terminal state.
        """
        if self.frozen:
            raise excp.FrozenMachine()

        if state not in self._states:
            raise excp.NotFound(
                f"Can not add a reaction to event '{event}' for an "
                f"undefined state '{state}'"
            )

        if not callable(reaction):
            raise ValueError("Reaction callback must be callable")

        if event in self._states[state]['reactions']:
            raise excp.Duplicate(
                f"State '{state}' reaction to event '{event}' already defined"
            )

        self._states[state]['reactions'][event] = (reaction, args, kwargs)

    def add_transition(
        self, start: str, end: str, event: str, replace: bool = False
    ) -> None:
        """Adds an allowed transition from start -> end for the given event.

        :param start: starting state
        :param end: ending state
        :param event: event that causes start state to
                      transition to end state
        :param replace: replace existing event instead of raising a
                        :py:class:`~automaton.exceptions.Duplicate` exception
                        when the transition already exists.
        """
        if self.frozen:
            raise excp.FrozenMachine()
        if start not in self._states:
            raise excp.NotFound(
                f"Can not add a transition on event '{event}' that "
                f"starts in a undefined state '{start}'"
            )
        if end not in self._states:
            raise excp.NotFound(
                f"Can not add a transition on event '{event}' that "
                f"ends in a undefined state '{end}'"
            )
        if self._states[start]['terminal']:
            raise excp.InvalidState(
                f"Can not add a transition on event '{event}' "
                f"that starts in the terminal state '{start}'"
            )
        if event in self._transitions[start] and not replace:
            target = self._transitions[start][event]
            if target.name != end:
                raise excp.Duplicate(
                    f"Cannot add transition from '{start}' to '{end}' "
                    f"on event '{event}' because a transition from '{start}' "
                    f"to '{target.name}' on event '{event}' already exists."
                )
        else:
            target = _Jump(
                end,
                self._states[end]['on_enter'],
                self._states[start]['on_exit'],
            )
            self._transitions[start][event] = target

    def _pre_process_event(self, event: str) -> None:
        current = self._current
        if current is None:
            raise excp.NotInitialized(
                f"Can not process event '{event}'; the state machine hasn't "
                f"been initialized"
            )
        if self._states[current.name]['terminal']:
            raise excp.InvalidState(
                f"Can not transition from terminal state '{current.name}' on "
                f"event '{event}'"
            )
        if event not in self._transitions[current.name]:
            raise excp.NotFound(
                f"Can not transition from state '{current.name}' on event "
                f"'{event}' (no defined transition)"
            )

    def _post_process_event(self, event: str, result: Effect) -> Effect:
        return result

    def process_event(self, event: str) -> Effect:
        """Trigger a state change in response to the provided event.

        :returns: Effect this is either a :py:class:`.FiniteMachine.Effect` or
                  an ``Effect`` from a subclass of :py:class:`.FiniteMachine`.
                  See the appropriate named tuple for a description of the
                  actual items in the tuple. For
                  example, :py:class:`.FiniteMachine.Effect`'s
                  first item is ``reaction``: one could invoke this reaction's
                  callback to react to the new stable state.
        :rtype: namedtuple
        """
        self._pre_process_event(event)
        current = self._current
        # narrow type (_pre_process_event ensures this)
        assert current is not None  # noqa: S101
        replacement = self._transitions[current.name][event]
        if current.on_exit is not None:
            current.on_exit(current.name, event)
        if replacement.on_enter is not None:
            replacement.on_enter(replacement.name, event)
        self._current = replacement
        result = self._effect_builder(self._states[replacement.name], event)
        return self._post_process_event(event, result)

    def initialize(self, start_state: str | None = None) -> None:
        """Sets up the state machine (sets current state to start state...).

        :param start_state: explicit start state to use to initialize the
                            state machine to. If ``None`` is provided then
                            the machine's default start state will be used
                            instead.
        """
        if start_state is None:
            start_state = self._default_start_state
        if start_state not in self._states:
            raise excp.NotFound(
                f"Can not start from a undefined state '{start_state}'"
            )
        if self._states[start_state]['terminal']:
            raise excp.InvalidState(
                f"Can not start from a terminal state '{start_state}'"
            )
        # No on enter will be called, since we are priming the state machine
        # and have not really transitioned from anything to get here, we will
        # though allow on_exit to be called on the event that causes this
        # to be moved from...
        self._current = _Jump(
            start_state, None, self._states[start_state]['on_exit']
        )

    def copy(self, shallow: bool = False, unfreeze: bool = False) -> Self:
        """Copies the current state machine.

        NOTE(harlowja): the copy will be left in an *uninitialized* state.

        NOTE(harlowja): when a shallow copy is requested the copy will share
                        the same transition table and state table as the
                        source; this can be advantageous if you have a machine
                        and transitions + states that is defined somewhere
                        and want to use copies to run with (the copies have
                        the current state that is different between machines).
        """
        c = type(self)()
        c._default_start_state = self._default_start_state
        if unfreeze and self.frozen:
            c.frozen = False
        else:
            c.frozen = self.frozen
        if not shallow:
            for state_name, state in self._states.items():
                copied_state = state.copy()
                copied_state['reactions'] = copied_state['reactions'].copy()
                c._states[state_name] = copied_state
            for state_name, transition in self._transitions.items():
                c._transitions[state_name] = transition.copy()
        else:
            c._transitions = self._transitions
            c._states = self._states
        return c

    def __contains__(self, state: str) -> bool:
        """Returns if this state exists in the machines known states."""
        return state in self._states

    def freeze(self) -> None:
        """Freezes & stops addition of states, transitions, reactions..."""
        self.frozen = True

    @property
    def states(self) -> list[str]:
        """Returns the state names."""
        return list(self._states)

    @property
    def events(self) -> int:
        """Returns how many events exist."""
        c = 0
        for state in self._states:
            c += len(self._transitions[state])
        return c

    def __iter__(self) -> Generator[tuple[str, str, str], None, None]:
        """Iterates over (start, event, end) transition tuples."""
        for state in self._states:
            for event, target in self._transitions[state].items():
                yield (state, event, target.name)

    def pformat(self, sort: bool = True, empty: str = '.') -> str:
        """Pretty formats the state + transition table into a string.

        NOTE(harlowja): the sort parameter can be provided to sort the states
        and transitions by sort order; with it being provided as false the rows
        will be iterated in addition order instead.
        """
        tbl = prettytable.PrettyTable(
            ["Start", "Event", "End", "On Enter", "On Exit"]
        )
        for state in _orderedkeys(self._states, sort=sort):
            prefix_markings = []
            if self.current_state == state:
                prefix_markings.append("@")
            postfix_markings = []
            if self.default_start_state == state:
                postfix_markings.append("^")
            if self._states[state]['terminal']:
                postfix_markings.append("$")
            pretty_state = "{}{}".format("".join(prefix_markings), state)
            if postfix_markings:
                pretty_state += "[{}]".format("".join(postfix_markings))
            if self._transitions[state]:
                for event in _orderedkeys(self._transitions[state], sort=sort):
                    target = self._transitions[state][event]
                    row = [pretty_state, event, target.name]
                    if target.on_enter is not None:
                        row.append(utils.get_callback_name(target.on_enter))
                    else:
                        row.append(empty)
                    if target.on_exit is not None:
                        row.append(utils.get_callback_name(target.on_exit))
                    else:
                        row.append(empty)
                    tbl.add_row(row)
            else:
                on_enter_cb = self._states[state]['on_enter']
                if on_enter_cb is not None:
                    on_enter = utils.get_callback_name(on_enter_cb)
                else:
                    on_enter = empty
                on_exit_cb = self._states[state]['on_exit']
                if on_exit_cb is not None:
                    on_exit = utils.get_callback_name(on_exit_cb)
                else:
                    on_exit = empty
                tbl.add_row([pretty_state, empty, empty, on_enter, on_exit])
        return tbl.get_string()


class HierarchicalFiniteMachine(FiniteMachine):
    """A fsm that understands how to run in a hierarchical mode."""

    #: The result of processing an event (cause and effect...)
    Effect = collections.namedtuple('Effect', 'reaction,terminal,machine')

    def __init__(self) -> None:
        super().__init__()
        self._nested_machines: dict[str, FiniteMachine] = {}

    @classmethod
    def _effect_builder(  # type: ignore[override]
        cls, new_state: Mapping[str, Any], event: str
    ) -> Effect:
        return cls.Effect(
            new_state['reactions'].get(event),
            new_state["terminal"],
            new_state.get('machine'),
        )

    def add_state(
        self,
        state: str,
        terminal: bool = False,
        on_enter: OnEnterCallbackT = None,
        on_exit: OnExitCallbackT = None,
        machine: 'FiniteMachine | None' = None,
    ) -> None:
        """Adds a given state to the state machine.

        :param machine: the nested state machine that will be transitioned
                        into when this state is entered

        Further arguments are interpreted as
        for :py:meth:`.FiniteMachine.add_state`.
        """
        if machine is not None and not isinstance(machine, FiniteMachine):
            raise ValueError(
                "Nested state machines must themselves be state machines"
            )
        super().add_state(
            state, terminal=terminal, on_enter=on_enter, on_exit=on_exit
        )
        if machine is not None:
            self._states[state]['machine'] = machine
            self._nested_machines[state] = machine

    def copy(self, shallow: bool = False, unfreeze: bool = False) -> Self:
        c = super().copy(shallow=shallow, unfreeze=unfreeze)
        if shallow:
            c._nested_machines = self._nested_machines
        else:
            c._nested_machines = self._nested_machines.copy()
        return c

    def initialize(
        self,
        start_state: str | None = None,
        nested_start_state_fetcher: Callable[['FiniteMachine'], str | None]
        | None = None,
    ) -> None:
        """Sets up the state machine (sets current state to start state...).

        :param start_state: explicit start state to use to initialize the
                            state machine to. If ``None`` is provided then the
                            machine's default start state will be used
                            instead.
        :param nested_start_state_fetcher: A callback that can return start
                                           states for any nested machines
                                           **only**. If not ``None`` then it
                                           will be provided a single argument,
                                           the machine to provide a starting
                                           state for and it is expected to
                                           return a starting state (or
                                           ``None``) for each machine called
                                           with. Do note that this callback
                                           will also be passed to other nested
                                           state machines as well, so it will
                                           also be used to initialize any state
                                           machines they contain (recursively).
        """
        super().initialize(start_state=start_state)
        for data in self._states.values():
            if 'machine' in data:
                nested_machine = data['machine']
                nested_start_state = None
                if nested_start_state_fetcher is not None:
                    nested_start_state = nested_start_state_fetcher(
                        nested_machine
                    )
                if isinstance(nested_machine, HierarchicalFiniteMachine):
                    nested_machine.initialize(
                        start_state=nested_start_state,
                        nested_start_state_fetcher=nested_start_state_fetcher,
                    )
                else:
                    nested_machine.initialize(start_state=nested_start_state)

    @property
    def nested_machines(self) -> dict[str, 'FiniteMachine']:
        """Dictionary of **all** nested state machines this machine may use."""
        return self._nested_machines

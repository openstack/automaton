# -*- coding: utf-8 -*-

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

from automaton import exceptions as excp
from automaton import fsm

import six
from testtools import testcase


class FSMTest(testcase.TestCase):
    def setUp(self):
        super(FSMTest, self).setUp()
        # NOTE(harlowja): this state machine will never stop if run() is used.
        self.jumper = fsm.FSM("down")
        self.jumper.add_state('up')
        self.jumper.add_state('down')
        self.jumper.add_transition('down', 'up', 'jump')
        self.jumper.add_transition('up', 'down', 'fall')
        self.jumper.add_reaction('up', 'jump', lambda *args: 'fall')
        self.jumper.add_reaction('down', 'fall', lambda *args: 'jump')

    def test_bad_start_state(self):
        m = fsm.FSM('unknown')
        self.assertRaises(excp.NotFound, m.run, 'unknown')

    def test_contains(self):
        m = fsm.FSM('unknown')
        self.assertNotIn('unknown', m)
        m.add_state('unknown')
        self.assertIn('unknown', m)

    def test_duplicate_state(self):
        m = fsm.FSM('unknown')
        m.add_state('unknown')
        self.assertRaises(excp.Duplicate, m.add_state, 'unknown')

    def test_duplicate_reaction(self):
        self.assertRaises(
            # Currently duplicate reactions are not allowed...
            excp.Duplicate,
            self.jumper.add_reaction, 'down', 'fall', lambda *args: 'skate')

    def test_bad_transition(self):
        m = fsm.FSM('unknown')
        m.add_state('unknown')
        m.add_state('fire')
        self.assertRaises(excp.NotFound, m.add_transition,
                          'unknown', 'something', 'boom')
        self.assertRaises(excp.NotFound, m.add_transition,
                          'something', 'unknown', 'boom')

    def test_bad_reaction(self):
        m = fsm.FSM('unknown')
        m.add_state('unknown')
        self.assertRaises(excp.NotFound, m.add_reaction, 'something', 'boom',
                          lambda *args: 'cough')

    def test_run(self):
        m = fsm.FSM('down')
        m.add_state('down')
        m.add_state('up')
        m.add_state('broken', terminal=True)
        m.add_transition('down', 'up', 'jump')
        m.add_transition('up', 'broken', 'hit-wall')
        m.add_reaction('up', 'jump', lambda *args: 'hit-wall')
        self.assertEqual(['broken', 'down', 'up'], sorted(m.states))
        self.assertEqual(2, m.events)
        m.initialize()
        self.assertEqual('down', m.current_state)
        self.assertFalse(m.terminated)
        m.run('jump')
        self.assertTrue(m.terminated)
        self.assertEqual('broken', m.current_state)
        self.assertRaises(excp.InvalidState, m.run, 'jump', initialize=False)

    def test_on_enter_on_exit(self):
        enter_transitions = []
        exit_transitions = []

        def on_exit(state, event):
            exit_transitions.append((state, event))

        def on_enter(state, event):
            enter_transitions.append((state, event))

        m = fsm.FSM('start')
        m.add_state('start', on_exit=on_exit)
        m.add_state('down', on_enter=on_enter, on_exit=on_exit)
        m.add_state('up', on_enter=on_enter, on_exit=on_exit)
        m.add_transition('start', 'down', 'beat')
        m.add_transition('down', 'up', 'jump')
        m.add_transition('up', 'down', 'fall')

        m.initialize()
        m.process_event('beat')
        m.process_event('jump')
        m.process_event('fall')
        self.assertEqual([('down', 'beat'),
                          ('up', 'jump'), ('down', 'fall')], enter_transitions)
        self.assertEqual([('down', 'jump'), ('up', 'fall')], exit_transitions)

    def test_run_iter(self):
        up_downs = []
        for (old_state, new_state) in self.jumper.run_iter('jump'):
            up_downs.append((old_state, new_state))
            if len(up_downs) >= 3:
                break
        self.assertEqual([('down', 'up'), ('up', 'down'), ('down', 'up')],
                         up_downs)
        self.assertFalse(self.jumper.terminated)
        self.assertEqual('up', self.jumper.current_state)
        self.jumper.process_event('fall')
        self.assertEqual('down', self.jumper.current_state)

    def test_run_send(self):
        up_downs = []
        it = self.jumper.run_iter('jump')
        while True:
            up_downs.append(it.send(None))
            if len(up_downs) >= 3:
                it.close()
                break
        self.assertEqual('up', self.jumper.current_state)
        self.assertFalse(self.jumper.terminated)
        self.assertEqual([('down', 'up'), ('up', 'down'), ('down', 'up')],
                         up_downs)
        self.assertRaises(StopIteration, six.next, it)

    def test_run_send_fail(self):
        up_downs = []
        it = self.jumper.run_iter('jump')
        up_downs.append(six.next(it))
        self.assertRaises(excp.NotFound, it.send, 'fail')
        it.close()
        self.assertEqual([('down', 'up')], up_downs)

    def test_not_initialized(self):
        self.assertRaises(excp.NotInitialized,
                          self.jumper.process_event, 'jump')

    def test_copy_states(self):
        c = fsm.FSM('down')
        self.assertEqual(0, len(c.states))
        d = c.copy()
        c.add_state('up')
        c.add_state('down')
        self.assertEqual(2, len(c.states))
        self.assertEqual(0, len(d.states))

    def test_copy_reactions(self):
        c = fsm.FSM('down')
        d = c.copy()

        c.add_state('down')
        c.add_state('up')
        c.add_reaction('down', 'jump', lambda *args: 'up')
        c.add_transition('down', 'up', 'jump')

        self.assertEqual(1, c.events)
        self.assertEqual(0, d.events)
        self.assertNotIn('down', d)
        self.assertNotIn('up', d)
        self.assertEqual([], list(d))
        self.assertEqual([('down', 'jump', 'up')], list(c))

    def test_copy_initialized(self):
        j = self.jumper.copy()
        self.assertIsNone(j.current_state)

        for i, transition in enumerate(self.jumper.run_iter('jump')):
            if i == 4:
                break

        self.assertIsNone(j.current_state)
        self.assertIsNotNone(self.jumper.current_state)

    def test_iter(self):
        transitions = list(self.jumper)
        self.assertEqual(2, len(transitions))
        self.assertIn(('up', 'fall', 'down'), transitions)
        self.assertIn(('down', 'jump', 'up'), transitions)

    def test_freeze(self):
        self.jumper.freeze()
        self.assertRaises(excp.FrozenMachine, self.jumper.add_state, 'test')
        self.assertRaises(excp.FrozenMachine,
                          self.jumper.add_transition, 'test', 'test', 'test')
        self.assertRaises(excp.FrozenMachine,
                          self.jumper.add_reaction,
                          'test', 'test', lambda *args: 'test')

    def test_invalid_callbacks(self):
        m = fsm.FSM('working')
        m.add_state('working')
        m.add_state('broken')
        self.assertRaises(ValueError, m.add_state, 'b', on_enter=2)
        self.assertRaises(ValueError, m.add_state, 'b', on_exit=2)

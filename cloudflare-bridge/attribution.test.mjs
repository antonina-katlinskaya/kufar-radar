import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldRepairAnastasiaOwner } from './worker.mjs';

test("Anastasia's observed ads recover from synthetic market account profiles', () => {
  assert.equal(shouldRepairAnastasiaOwner('account:some-id','8517496'),true);
  assert.equal(shouldRepairAnastasiaOwner('account:another-id',8517496),true);
});

test('No changes to already assigned or other verified numeric profiles', () => {
  assert.equal(shouldRepairAnastasiaOwner('8517496','8517496'),false);
  assert.equal(shouldRepairAnastasiaOwner('11093294','8517496'),false);
  assert.equal(shouldRepairAnastasiaOwner('account:some-id','11093294'),false);
  assert.equal(shouldRepairAnastasiaOwner(null,'8517496'),false);
});

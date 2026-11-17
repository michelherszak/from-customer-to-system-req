import test from 'node:test'
import assert from 'node:assert/strict'
import { formatHttpError, readHttpError } from '../src/httpErrors.ts'

test('HTML gateway errors read the response once and retain HTTP status', async () => {
  const response = new Response('<!DOCTYPE html><html><body>Bad Gateway</body></html>', {status:502,statusText:'Bad Gateway'})
  assert.equal(await readHttpError(response),'502 Bad Gateway')
  assert.equal(response.bodyUsed,true)
})

test('JSON API errors preserve the server detail', async () => {
  const response = new Response(JSON.stringify({detail:'Kein Projektzugriff'}),{status:403})
  assert.equal(await readHttpError(response),'Kein Projektzugriff')
})

test('validation arrays remain available for troubleshooting', async () => {
  const detail=[{loc:['body','name'],msg:'Field required',type:'missing'}]
  assert.equal(await readHttpError(new Response(JSON.stringify({detail}),{status:422})),JSON.stringify(detail))
})

test('plain text and malformed JSON errors do not require another body read', async () => {
  for(const body of ['Service unavailable','{"broken":']) {
    assert.equal(await readHttpError(new Response(body,{status:503})),body)
  }
})

test('empty and null error bodies have a useful status fallback', async () => {
  for(const body of ['', 'null', '{"detail":null}', '{"detail":""}']) {
    assert.equal(await readHttpError(new Response(body,{status:500,statusText:'Internal Server Error'})),'500 Internal Server Error')
  }
})

test('JSON strings and structured upload errors use the same formatter', () => {
  assert.equal(formatHttpError('"Upload failed"',400),'Upload failed')
  assert.equal(formatHttpError('{"detail":{"code":"conflict"}}',409),'{"code":"conflict"}')
})

/* Create least-privilege application users on the first MongoDB startup. */
const users = [
  { db: 'gateway', user: 'gateway', password: process.env.MONGO_GATEWAY_PASSWORD },
  {
    db: 'files',
    user: 'files',
    password: process.env.MONGO_FILES_PASSWORD,
    roles: [{ role: 'readWrite', db: 'files' }, { role: 'readWrite', db: 'audit_trail' }],
  },
  {
    db: 'memory',
    user: 'memory',
    password: process.env.MONGO_MEMORY_PASSWORD,
    roles: [{ role: 'readWrite', db: 'chats' }],
  },
  { db: 'rag', user: 'rag', password: process.env.MONGO_RAG_PASSWORD },
]

for (const entry of users) {
  if (!entry.password || entry.password.length < 16) {
    throw new Error(`Missing or weak MongoDB password for ${entry.user}`)
  }
  db.getSiblingDB(entry.db).createUser({
    user: entry.user,
    pwd: entry.password,
    roles: entry.roles || [{ role: 'readWrite', db: entry.db }],
  })
}

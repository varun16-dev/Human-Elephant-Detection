# Create .env file with proper formatting for dotenv
content = """VAPID_PUBLIC_KEY=04a24de2bdd98316e58e898a7e1225b23b9af5ad7b245295f843d8c472aaaee92d844e319f1d253839a1e6922b98f34ee21cbb0df5bf10c47a7be6ce530b3eec37
VAPID_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgOwB/pTd70sQTLA6/\\nuA3phGa83rvy5/udX/acG0mkeKahRANCAASiTeK92YMW5Y6Jin4SJbI7mvWteyRS\\nlfhD2MRyqq7pLYROMZ8dJTg5oeaSK5jzTuIcuw31vxDEenvmzlMLPuw3\\n-----END PRIVATE KEY-----"
VAPID_CLAIMS_EMAIL=admin@example.com
"""

with open('.env', 'w') as f:
    f.write(content)
print(".env file created successfully with proper formatting")

pipeline {
agent any

stages {

stage('Checkout') {
steps {
git branch: 'main',
url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
}
}

stage('Deploy') {
steps {
sh '''
cd /root/rankersacademy

git pull origin main

# rebuild latest image
docker compose build web

# recreate only app container (db untouched)
docker compose up -d --no-deps --force-recreate web

# cleanup old dangling images
docker image prune -f
'''
}
}

stage('Health Check'){
steps{
sh 'curl -I http://127.0.0.1:8081'
}
}

}

post {
success {
echo "New container deployed successfully"
}
failure {
echo "Deployment failed"
}
}
}

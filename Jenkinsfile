pipeline {
agent any

stages {

stage('Clone'){
steps{
git branch: 'main',
url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
}
}

stage('Build'){
steps{
sh 'docker compose build --no-cache'
}
}

stage('Deploy'){
steps{
sh '''
docker compose up -d --build
docker image prune -f
'''
}
}

stage('Health Check'){
steps{
sh 'curl -I https://rankersonlinetest.com'
}
}

}

post {
success {
echo 'Deployment Successful'
}
failure {
echo 'Build Failed'
}
}
}

pipeline {
agent any

stages {

stage('Checkout Code'){
steps{
git branch: 'main',
url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
}
}

stage('Docker Build'){
steps{
sh '''
docker compose -p rankersacademy build web
'''
}
}

stage('Docker Deploy'){
steps{
sh '''
docker compose -p rankersacademy up -d --no-deps --force-recreate web
'''
}
}

stage('Docker Cleanup'){
steps{
sh '''
docker image prune -f
'''
}
}

stage('Health Check'){
steps{
sh '''
sleep 15
curl -f https://rankersonlinetest.com
'''
}
}

}

post {
success {
echo 'Deployment Successful'
}

failure {
echo 'Deployment Failed'
}

always {
sh 'docker ps'
}
}
}

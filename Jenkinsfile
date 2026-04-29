pipeline {
agent any

stages {

stage('Checkout'){
steps{
git branch: 'main',
url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
}
}

stage('Deploy'){
steps{
sh '''
docker compose build web
docker compose up -d --no-deps --force-recreate web
docker image prune -f
'''
}
}

stage('Health Check'){
steps{
sh '''
sleep 10
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
}
}

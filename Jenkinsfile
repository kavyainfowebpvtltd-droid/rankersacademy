pipeline {
agent any

environment {
APP_NAME="rankersacademy"
}

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
docker compose down
docker compose up -d
'''
}
}

}

post {
success {
echo "Deployment Success"
}
}
}

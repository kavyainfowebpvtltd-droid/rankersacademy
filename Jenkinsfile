pipeline {
agent any

```
stages {

    stage('Checkout Code') {
        steps {
            git branch: 'main',
                url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
        }
    }

    stage('Docker Build') {
        steps {
            sh '''
            docker compose -p rankersacademy build web
            '''
        }
    }

    stage('Docker Deploy') {
        steps {
            sh '''
            echo "Stopping old containers..."
            docker compose -p rankersacademy down

            echo "Starting containers..."
            docker compose -p rankersacademy up -d --build

            echo "Waiting for services..."
            sleep 20

            echo "Running migrations..."
            docker exec rankers-app python manage.py migrate

            echo "Collecting static files..."
            docker exec rankers-app python manage.py collectstatic --noinput

            echo "Cleaning old images..."
            docker image prune -f
            '''
        }
    }

    stage('Verify Deployment') {
        steps {
            sh '''
            echo "Container Status:"
            docker ps

            echo "Port Mapping:"
            docker inspect rankers-app --format '{{json .HostConfig.PortBindings}}'

            echo "Application Health Check:"
            curl -I http://127.0.0.1:8081 || true
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
        sh '''
        echo "Running Containers:"
        docker ps
        '''
    }
}
```

}

